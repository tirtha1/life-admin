"""
JWT security utilities — RS256 verification + user extraction.
"""
import os
import structlog
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError

log = structlog.get_logger()

JWT_PUBLIC_KEY = os.environ.get("JWT_PUBLIC_KEY", "")
JWT_ALGORITHM = "RS256"
JWT_AUDIENCE = os.environ.get("JWT_AUDIENCE", "lifeadmin-api")

# Fallback to HS256 with a shared secret for dev (when no RSA key is set)
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-secret-change-me")
JWT_DEV_ALGORITHM = "HS256"

_bearer = HTTPBearer(auto_error=True)


def _decode_token(token: str) -> dict:
    """Decode and verify a JWT. Raises HTTPException on failure."""
    try:
        if JWT_PUBLIC_KEY:
            payload = jwt.decode(
                token,
                JWT_PUBLIC_KEY,
                algorithms=[JWT_ALGORITHM],
                audience=JWT_AUDIENCE,
            )
        else:
            # Dev mode: HS256 with shared secret
            payload = jwt.decode(
                token,
                JWT_SECRET_KEY,
                algorithms=[JWT_DEV_ALGORITHM],
            )
        return payload
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


class CurrentUser:
    """Represents the authenticated user extracted from JWT."""

    def __init__(self, user_id: str, email: str, payload: dict):
        self.user_id = user_id
        self.email = email
        self.payload = payload

    def __repr__(self) -> str:
        return f"CurrentUser(user_id={self.user_id}, email={self.email})"


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> CurrentUser:
    """FastAPI dependency — validates Bearer token and returns CurrentUser."""
    payload = _decode_token(credentials.credentials)

    user_id = payload.get("sub") or payload.get("user_id")
    email = payload.get("email", "")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing 'sub' claim",
        )

    log.debug("Authenticated", user_id=user_id, email=email)
    return CurrentUser(user_id=user_id, email=email, payload=payload)


def create_dev_token(user_id: str, email: str) -> str:
    """
    Create a dev HS256 token for local testing.
    NOT for production use.
    """
    import jwt as _jwt
    payload = {
        "sub": user_id,
        "email": email,
        "iat": datetime.now(timezone.utc),
    }
    return _jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_DEV_ALGORITHM)
