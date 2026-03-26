"""
OAuth token manager — refreshes tokens 5 minutes before expiry.
Stores refreshed tokens back to Vault and DB.
"""
import os
import structlog
from datetime import datetime, timezone, timedelta
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from shared.vault import get_vault_client

log = structlog.get_logger()

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

REFRESH_MARGIN = timedelta(minutes=5)


class TokenManager:
    """
    Manages OAuth tokens for a user.

    Usage:
        tm = TokenManager(user_id="uuid")
        creds = tm.get_valid_credentials()
    """

    def __init__(self, user_id: str, provider: str = "google"):
        self.user_id = user_id
        self.provider = provider
        self._vault = get_vault_client()

    def _load_tokens(self) -> Optional[dict]:
        """Load tokens from Vault."""
        return self._vault.get_oauth_tokens(self.user_id, self.provider)

    def _store_tokens(self, access_token: str, expiry: datetime) -> None:
        """Persist refreshed tokens to Vault."""
        tokens = self._vault.get_oauth_tokens(self.user_id, self.provider) or {}
        tokens["access_token"] = access_token
        tokens["expiry"] = expiry.isoformat()
        self._vault.store_oauth_tokens(self.user_id, self.provider, tokens)
        log.info("Tokens stored", user_id=self.user_id, provider=self.provider)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=5, max=60),
    )
    def get_valid_credentials(self) -> Credentials:
        """
        Return valid Google credentials, refreshing if needed.
        Raises if tokens not found in Vault.
        """
        tokens = self._load_tokens()
        if not tokens:
            raise ValueError(
                f"No OAuth tokens found for user={self.user_id} provider={self.provider}. "
                "Complete the OAuth flow first."
            )

        expiry_str = tokens.get("expiry")
        if expiry_str:
            expiry = datetime.fromisoformat(expiry_str)
            # Google's Credentials expects naive UTC datetime
            if expiry.tzinfo is not None:
                expiry = expiry.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            expiry = None

        creds = Credentials(
            token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            expiry=expiry,
        )

        # Refresh 5 minutes before actual expiry (expiry is naive UTC)
        needs_refresh = (
            not creds.valid
            or (expiry and datetime.utcnow() >= expiry - REFRESH_MARGIN)
        )

        if needs_refresh:
            log.info("Refreshing access token", user_id=self.user_id)
            creds.refresh(Request())
            self._store_tokens(creds.token, creds.expiry)

        return creds
