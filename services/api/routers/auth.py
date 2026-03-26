"""
Auth router — OAuth flow + dev token endpoint.
"""
import os
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from shared.db.models import OAuthToken, User
from shared.db.session import AsyncSessionLocal
from shared.vault.client import VaultClient
from services.api.security import create_dev_token

log = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["auth"])
legacy_router = APIRouter(prefix="/ingestion/oauth", tags=["auth"])

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
OAUTH_REDIRECT_URI = os.environ.get(
    "OAUTH_REDIRECT_URI",
    os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/v1/auth/callback"),
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


class OAuthCallbackResponse(BaseModel):
    message: str
    email: str
    user_id: str
    note: str
    access_token: str | None = None


def _ensure_google_oauth_configured() -> None:
    if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
        return
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
    )


def _normalize_expiry(expiry: datetime | None) -> datetime:
    if expiry is None:
        return datetime.now(timezone.utc)
    if expiry.tzinfo is None:
        return expiry.replace(tzinfo=timezone.utc)
    return expiry.astimezone(timezone.utc)


async def _upsert_google_connection(
    *,
    user_email: str,
    full_name: str | None,
    access_token: str,
    refresh_token: str | None,
    expiry: datetime,
    scopes: list[str],
) -> str:
    vault = _get_vault()

    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(select(User).where(User.email == user_email))
            user = result.scalar_one_or_none()

            if user is None:
                user = User(
                    email=user_email,
                    full_name=full_name or user_email.split("@")[0],
                )
                session.add(user)
                await session.flush()
            elif full_name and user.full_name != full_name:
                user.full_name = full_name

            existing_tokens = vault.get_oauth_tokens(user.id, "google") or {}
            effective_refresh_token = refresh_token or existing_tokens.get("refresh_token")
            if not effective_refresh_token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Google did not return a refresh token. Remove this app from your "
                        "Google account permissions and authorize again."
                    ),
                )

            vault.store_oauth_tokens(
                user.id,
                "google",
                {
                    "access_token": access_token,
                    "refresh_token": effective_refresh_token,
                    "expiry": expiry.isoformat(),
                },
            )

            result = await session.execute(
                select(OAuthToken).where(
                    OAuthToken.user_id == user.id,
                    OAuthToken.provider == "google",
                )
            )
            oauth_token = result.scalar_one_or_none()

            encrypted_access_token = vault.encrypt_token(access_token)
            encrypted_refresh_token = vault.encrypt_token(effective_refresh_token)

            if oauth_token is None:
                session.add(
                    OAuthToken(
                        user_id=user.id,
                        provider="google",
                        access_token=encrypted_access_token,
                        refresh_token=encrypted_refresh_token,
                        token_expiry=expiry,
                        scopes=scopes,
                    )
                )
            else:
                oauth_token.access_token = encrypted_access_token
                oauth_token.refresh_token = encrypted_refresh_token
                oauth_token.token_expiry = expiry
                oauth_token.scopes = scopes

            await session.commit()
            return user.id
        except Exception:
            await session.rollback()
            raise


@router.get("/google")
async def oauth_start():
    """Redirect the user to Google OAuth consent screen."""
    from google_auth_oauthlib.flow import Flow

    _ensure_google_oauth_configured()

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


@router.get("/callback", response_model=OAuthCallbackResponse)
async def oauth_callback(code: str = Query(...), state: str = Query(...)):
    """
    Exchange OAuth code for tokens and store in Vault.
    In production this should set a session/JWT and redirect to the frontend.
    """
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build

    _ensure_google_oauth_configured()

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
    user_id = await _upsert_google_connection(
        user_email=user_email,
        full_name=user_info.get("name"),
        access_token=creds.token or "",
        refresh_token=creds.refresh_token,
        expiry=_normalize_expiry(creds.expiry),
        scopes=list(creds.scopes or GOOGLE_SCOPES),
    )

    response = OAuthCallbackResponse(
        message="OAuth complete",
        email=user_email,
        user_id=user_id,
        note="Google tokens stored successfully.",
    )

    app_env = os.environ.get("APP_ENV", "development")
    if app_env != "production":
        response.access_token = create_dev_token(user_id, user_email)
        response.note = (
            "Google tokens stored successfully. Use the returned access_token for local API calls."
        )

    log.info("OAuth callback success", email=user_email, user_id=user_id)
    return response


@legacy_router.get("/start")
async def legacy_oauth_start():
    """Backward-compatible OAuth start route used by older docs/config."""
    return await oauth_start()


@legacy_router.get("/callback", response_model=OAuthCallbackResponse)
async def legacy_oauth_callback(code: str = Query(...), state: str = Query(...)):
    """Backward-compatible OAuth callback route used by older docs/config."""
    return await oauth_callback(code=code, state=state)


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
