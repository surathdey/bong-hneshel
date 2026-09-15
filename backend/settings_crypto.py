"""
Fernet-based encryption helper for storing integration secrets (Twilio Auth
Token, Google service-account JSON, etc.) in MongoDB.

Only the encryption key is stored in .env under `INTEGRATIONS_FERNET_KEY`.
The plaintext secrets NEVER touch disk or logs — only their ciphertext.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

load_dotenv()

_KEY = os.environ.get("INTEGRATIONS_FERNET_KEY", "").strip()
if not _KEY:
    # Not a hard error — the server should still boot; endpoints that need
    # decryption will 500 clearly if the key is missing.
    _FERNET: Optional[Fernet] = None
else:
    try:
        _FERNET = Fernet(_KEY.encode())
    except Exception:
        _FERNET = None


def _require() -> Fernet:
    if _FERNET is None:
        raise RuntimeError(
            "INTEGRATIONS_FERNET_KEY missing or invalid in backend/.env — "
            "cannot encrypt/decrypt integration secrets."
        )
    return _FERNET


def encrypt_str(plaintext: str) -> str:
    """Encrypt an arbitrary string and return the URL-safe base64 token."""
    return _require().encrypt(plaintext.encode()).decode()


def decrypt_str(token: str) -> str:
    """Reverse of encrypt_str. Raises RuntimeError on tampering."""
    try:
        return _require().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise RuntimeError("Encrypted secret is invalid or tampered") from e


def encrypt_service_account_json(raw_json: str) -> str:
    """Validate + encrypt a Google service-account JSON blob."""
    data = json.loads(raw_json)
    if data.get("type") != "service_account":
        raise ValueError("Not a Google service_account JSON key")
    for field in ("client_email", "private_key", "token_uri"):
        if not data.get(field):
            raise ValueError(f"Service-account JSON missing field: {field}")
    # Re-serialize (normalizes whitespace) then encrypt.
    return encrypt_str(json.dumps(data))


def decrypt_service_account_json(token: str) -> dict:
    return json.loads(decrypt_str(token))


def is_configured() -> bool:
    return _FERNET is not None
