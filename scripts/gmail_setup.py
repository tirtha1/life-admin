"""
One-time Gmail OAuth setup.
Run this locally to authorize Gmail access and store tokens in Vault.

Usage:
    python scripts/gmail_setup.py --user-id 00000000-0000-0000-0000-000000000001
"""
import argparse
import json
import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow
import requests

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

VAULT_ADDR = os.environ.get("VAULT_ADDR", "http://localhost:8200")
VAULT_TOKEN = os.environ.get("VAULT_TOKEN", os.environ.get("VAULT_DEV_TOKEN", "devtoken"))

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")


def do_oauth_flow() -> dict:
    client_config = {
        "installed": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)

    return {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }


def store_in_vault(user_id: str, tokens: dict) -> None:
    path = f"secret/data/life-admin/oauth/{user_id}/google"
    url = f"{VAULT_ADDR}/v1/{path}"
    headers = {"X-Vault-Token": VAULT_TOKEN}
    payload = {"data": tokens}

    resp = requests.post(url, json=payload, headers=headers)
    if resp.status_code not in (200, 204):
        print(f"[ERROR] Vault write failed: {resp.status_code} {resp.text}")
        sys.exit(1)

    print(f"[OK] Tokens stored in Vault at life-admin/oauth/{user_id}/google")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", required=True, help="Your user UUID")
    args = parser.parse_args()

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        print("[ERROR] GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in environment")
        sys.exit(1)

    print("Opening browser for Google OAuth...")
    print("Sign in with the Gmail account you want to monitor.\n")

    tokens = do_oauth_flow()
    print(f"[OK] Got tokens (refresh_token={'yes' if tokens.get('refresh_token') else 'NO - re-run'})")

    store_in_vault(args.user_id, tokens)
    print("\nDone! Gmail is now connected.")
    print(f"Trigger a sync: POST http://localhost:8000/api/v1/ingestion/sync")


if __name__ == "__main__":
    main()
