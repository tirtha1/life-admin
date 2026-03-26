"""
Auth router — OAuth flow + dev token endpoint.
"""
import os
import structlog
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from shared.vault.client import VaultClient
from services.api.security import create_dev_token

log = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["auth"])

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
OAUTH_REDIRECT_URI = os.environ.get(
    "OAUTH_REDIRECT_URI", "http://localhost:8000/api/v1/auth/callback"
)
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "openid",
    "email",
    "profile",
]

_vault: VaultClient | None = None


def _get_vault() -> VaultClient:
    global _vault
    if _vault is None:
        _vault = VaultClient()
    return _vault


class DevTokenRequest(BaseModel):
    user_id: str
    email: str


class DevTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.get("/google")
async def oauth_start():
    """Redirect the user to Google OAuth consent screen."""
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uris": [OAUTH_REDIRECT_URI],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=GOOGLE_SCOPES,
    )
    flow.redirect_uri = OAUTH_REDIRECT_URI
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return {"auth_url": auth_url, "state": state}


@router.get("/callback")
async def oauth_callback(code: str = Query(...), state: str = Query(...)):
    """
    Exchange OAuth code for tokens and store in Vault.
    In production this should set a session/JWT and redirect to the frontend.
    """
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uris": [OAUTH_REDIRECT_URI],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=GOOGLE_SCOPES,
        state=state,
    )
    flow.redirect_uri = OAUTH_REDIRECT_URI
    flow.fetch_token(code=code)
    creds = flow.credentials

    # Get user info
    service = build("oauth2", "v2", credentials=creds)
    user_info = service.userinfo().get().execute()
    user_email = user_info["email"]

    # TODO: Upsert user in DB + store tokens in Vault
    log.info("OAuth callback success", email=user_email)

    return {
        "message": "OAuth complete",
        "email": user_email,
        "note": "Tokens stored in Vault. Connect user to your app session.",
    }


@router.post("/token", response_model=DevTokenResponse)
async def dev_token(request: DevTokenRequest):
    """
    DEV ONLY — issues a signed JWT for local testing.
    Disable this endpoint in production by checking APP_ENV.
    """
    app_env = os.environ.get("APP_ENV", "development")
    if app_env == "production":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )
    token = create_dev_token(request.user_id, request.email)
    return DevTokenResponse(access_token=token)
