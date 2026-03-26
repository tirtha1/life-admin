"""
HashiCorp Vault client wrapper.
- AppRole auth (Role ID + Secret ID)
- In-memory secret caching with TTL
- Token auto-renewal
- AES-256-GCM encryption for OAuth tokens
"""
import os
import json
import time
import base64
import structlog
from typing import Any, Optional
from functools import lru_cache

import hvac
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

log = structlog.get_logger()

VAULT_ADDR = os.environ.get("VAULT_ADDR", "http://localhost:8200")
VAULT_DEV_TOKEN = os.environ.get("VAULT_DEV_TOKEN", "devtoken")
VAULT_ROLE_ID = os.environ.get("VAULT_ROLE_ID", "")
VAULT_SECRET_ID = os.environ.get("VAULT_SECRET_ID", "")

# Cache TTL in seconds
CACHE_TTL = 300  # 5 minutes


class VaultClient:
    """
    Vault client with AppRole auth, secret caching, and OAuth token encryption.

    In development (no VAULT_ROLE_ID set), falls back to dev token auth.
    """

    def __init__(self):
        self._client = hvac.Client(url=VAULT_ADDR)
        self._cache: dict[str, tuple[Any, float]] = {}  # key → (value, expiry_ts)
        self._authenticate()

    def _authenticate(self) -> None:
        """Authenticate with Vault using AppRole or dev token."""
        if VAULT_ROLE_ID and VAULT_SECRET_ID:
            result = self._client.auth.approle.login(
                role_id=VAULT_ROLE_ID,
                secret_id=VAULT_SECRET_ID,
            )
            self._client.token = result["auth"]["client_token"]
            log.info("Vault: authenticated via AppRole")
        else:
            # Dev mode: use root token
            self._client.token = VAULT_DEV_TOKEN
            log.warning("Vault: using dev token (not for production!)")

    def _ensure_authenticated(self) -> None:
        """Re-authenticate if token is expired."""
        if not self._client.is_authenticated():
            log.info("Vault: re-authenticating")
            self._authenticate()

    def get_secret(self, path: str) -> dict[str, Any]:
        """
        Fetch a secret from Vault KV v2.
        Results are cached for CACHE_TTL seconds.
        """
        now = time.time()
        if path in self._cache:
            value, expiry = self._cache[path]
            if now < expiry:
                return value

        self._ensure_authenticated()
        try:
            result = self._client.secrets.kv.v2.read_secret_version(path=path)
            data = result["data"]["data"]
            self._cache[path] = (data, now + CACHE_TTL)
            log.debug("Vault: secret fetched", path=path)
            return data
        except Exception as e:
            log.error("Vault: failed to fetch secret", path=path, error=str(e))
            raise

    def set_secret(self, path: str, data: dict[str, Any]) -> None:
        """Store a secret in Vault KV v2."""
        self._ensure_authenticated()
        self._client.secrets.kv.v2.create_or_update_secret(path=path, secret=data)
        # Invalidate cache
        self._cache.pop(path, None)
        log.info("Vault: secret stored", path=path)

    # ─── OAuth token helpers ─────────────────────────────────────────────────

    def _get_encryption_key(self) -> bytes:
        """Retrieve AES-256 encryption key from Vault."""
        try:
            data = self.get_secret("life-admin/encryption-key")
            return base64.b64decode(data["key"])
        except Exception:
            # Fallback: derive from env SECRET_KEY (dev only!)
            secret = os.environ.get("SECRET_KEY", "insecure-dev-key-change-me")
            import hashlib
            return hashlib.sha256(secret.encode()).digest()

    def encrypt_token(self, plaintext: str) -> bytes:
        """AES-256-GCM encrypt an OAuth token string."""
        key = self._get_encryption_key()
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
        # Prepend nonce to ciphertext
        return nonce + ciphertext

    def decrypt_token(self, ciphertext: bytes) -> str:
        """AES-256-GCM decrypt an OAuth token."""
        key = self._get_encryption_key()
        aesgcm = AESGCM(key)
        nonce, ct = ciphertext[:12], ciphertext[12:]
        return aesgcm.decrypt(nonce, ct, None).decode()

    def store_oauth_tokens(
        self, user_id: str, provider: str, tokens: dict[str, str]
    ) -> None:
        """Store OAuth tokens for a user in Vault (unencrypted at Vault level — Vault encrypts its storage)."""
        path = f"life-admin/oauth/{user_id}/{provider}"
        self.set_secret(path, tokens)

    def get_oauth_tokens(self, user_id: str, provider: str) -> Optional[dict[str, str]]:
        """Retrieve OAuth tokens for a user from Vault."""
        path = f"life-admin/oauth/{user_id}/{provider}"
        try:
            return self.get_secret(path)
        except Exception:
            return None


# Singleton
_vault_client: Optional[VaultClient] = None


def get_vault_client() -> VaultClient:
    global _vault_client
    if _vault_client is None:
        _vault_client = VaultClient()
    return _vault_client
