"""
Auth router — OAuth flow + dev token endpoint.
"""
import os
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import delete as sql_delete, select

from shared.db.models import OAuthToken, User
from shared.db.session import AsyncSessionLocal
from shared.vault.client import VaultClient
from services.api.security import create_app_token, create_dev_token, get_current_user

log = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["auth"])
legacy_router = APIRouter(prefix="/ingestion/oauth", tags=["auth"])

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
OAUTH_REDIRECT_URI = os.environ.get(
    "OAUTH_REDIRECT_URI",
    os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/v1/auth/callback"),
)
# Desktop app credential — accepts lifeadminai:// redirect scheme used by mobile
GOOGLE_MOBILE_CLIENT_ID = os.environ.get("GOOGLE_MOBILE_CLIENT_ID", GOOGLE_CLIENT_ID)
GOOGLE_MOBILE_CLIENT_SECRET = os.environ.get("GOOGLE_MOBILE_CLIENT_SECRET", GOOGLE_CLIENT_SECRET)
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


class MobileAuthRequest(BaseModel):
    code: str
    redirect_uri: str


class MobileAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str


MOBILE_OAUTH_CALLBACK_URI = os.environ.get(
    "MOBILE_OAUTH_CALLBACK_URI",
    "http://localhost:8000/api/v1/auth/mobile-callback",
)


@router.get("/mobile-start")
async def mobile_oauth_start(app_redirect: str = Query(...)):
    """
    Start Google OAuth for Expo Go / mobile.
    Builds the Google auth URL manually so the redirect_uri is exactly what we register.
    """
    import base64
    import json
    import urllib.parse

    _ensure_google_oauth_configured()

    state_payload = base64.urlsafe_b64encode(
        json.dumps({"app_redirect": app_redirect}).encode()
    ).decode().rstrip("=")

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": MOBILE_OAUTH_CALLBACK_URI,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state_payload,
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    log.info("Mobile OAuth start", redirect_uri=MOBILE_OAUTH_CALLBACK_URI)
    return {"auth_url": auth_url}


@router.get("/mobile-callback")
async def mobile_oauth_callback(code: str = Query(...), state: str = Query(...)):
    """
    Google redirects here after the user authenticates.
    Exchanges code for tokens manually, creates an app JWT, redirects back to the app.
    """
    import base64
    import json
    import requests as http
    from fastapi.responses import RedirectResponse as HTTPRedirectResponse

    _ensure_google_oauth_configured()

    # Recover app_redirect from state
    try:
        padding = "=" * (-len(state) % 4)
        state_data = json.loads(base64.urlsafe_b64decode(state + padding))
        app_redirect = state_data.get("app_redirect", "lifeadminai://callback")
    except Exception:
        app_redirect = "lifeadminai://callback"

    # Exchange code for tokens directly
    try:
        token_resp = http.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": MOBILE_OAUTH_CALLBACK_URI,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()
    except Exception as exc:
        log.warning("Mobile OAuth token exchange failed", error=str(exc))
        return HTTPRedirectResponse(url=f"{app_redirect}?error=auth_failed")

    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token")

    # Get user info
    try:
        userinfo_resp = http.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        userinfo_resp.raise_for_status()
        user_info = userinfo_resp.json()
    except Exception as exc:
        log.warning("Mobile OAuth userinfo failed", error=str(exc))
        return HTTPRedirectResponse(url=f"{app_redirect}?error=auth_failed")

    from datetime import timedelta
    expiry = datetime.now(timezone.utc) + timedelta(seconds=token_data.get("expires_in", 3600))

    user_id = await _upsert_google_connection(
        user_email=user_info["email"],
        full_name=user_info.get("name"),
        access_token=access_token,
        refresh_token=refresh_token,
        expiry=expiry,
        scopes=GOOGLE_SCOPES,
    )

    token = create_app_token(user_id, user_info["email"])
    log.info("Mobile OAuth success", email=user_info["email"], user_id=user_id)
    return HTTPRedirectResponse(url=f"{app_redirect}?token={token}")


@router.post("/google/mobile", response_model=MobileAuthResponse)
async def mobile_google_auth(request: MobileAuthRequest):
    """
    Exchange a Google auth code from the mobile app for an app JWT.
    The mobile app (expo-auth-session) sends the code + the redirect_uri it used;
    the backend exchanges it with Google, upserts the user, and returns an app token.
    The phone never sees the Google refresh token.
    Uses GOOGLE_MOBILE_CLIENT_ID (Desktop app credential) which accepts lifeadminai:// scheme.
    """
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build

    if not GOOGLE_MOBILE_CLIENT_ID or not GOOGLE_MOBILE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mobile Google OAuth not configured. Set GOOGLE_MOBILE_CLIENT_ID and GOOGLE_MOBILE_CLIENT_SECRET.",
        )

    flow = Flow.from_client_config(
        {
            "installed": {
                "client_id": GOOGLE_MOBILE_CLIENT_ID,
                "client_secret": GOOGLE_MOBILE_CLIENT_SECRET,
                "redirect_uris": [request.redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=GOOGLE_SCOPES,
    )
    flow.redirect_uri = request.redirect_uri

    try:
        flow.fetch_token(code=request.code)
    except Exception as exc:
        log.warning("Mobile token exchange failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to exchange authorization code with Google. It may be expired or already used.",
        )

    creds = flow.credentials
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

    token = create_app_token(user_id, user_email)
    log.info("Mobile Google auth success", email=user_email, user_id=user_id)
    return MobileAuthResponse(
        access_token=token,
        user_id=user_id,
        email=user_email,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(current_user=Depends(get_current_user)):
    """
    Revoke the user's Google OAuth token and remove it from Vault + DB.
    The app JWT is stateless — instruct the client to discard it locally.
    """
    import requests as http

    vault = _get_vault()
    tokens = vault.get_oauth_tokens(current_user.user_id, "google") or {}
    access_token = tokens.get("access_token")

    if access_token:
        try:
            http.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": access_token},
                timeout=5,
            )
        except Exception:
            pass  # best-effort revocation

    async with AsyncSessionLocal() as session:
        try:
            await session.execute(
                sql_delete(OAuthToken).where(
                    OAuthToken.user_id == current_user.user_id,
                    OAuthToken.provider == "google",
                )
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    log.info("User logged out, Google token revoked", user_id=current_user.user_id)


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(current_user=Depends(get_current_user)):
    """
    Delete all user data: bills, transactions, OAuth tokens, and the user record.
    Irreversible. Client must discard the JWT after this call.
    """
    import requests as http

    vault = _get_vault()
    tokens = vault.get_oauth_tokens(current_user.user_id, "google") or {}
    access_token = tokens.get("access_token")

    if access_token:
        try:
            http.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": access_token},
                timeout=5,
            )
        except Exception:
            pass

    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                select(User).where(User.id == current_user.user_id)
            )
            user = result.scalar_one_or_none()
            if user:
                await session.delete(user)  # cascades via FK to all related rows
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    log.info("Account deleted", user_id=current_user.user_id)


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
