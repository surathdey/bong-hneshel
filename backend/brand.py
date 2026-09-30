"""
Backend brand config — one source of truth for brand-specific values
that appear in emails, receipts, SMS, and admin UI copy.

The values live in a JSON file (`brand.json`) at the repo root so that
Python and Node/Expo can both read the SAME source without a runtime
FFI. Whenever a new tenant forks this repo they only touch that JSON.

Fallback order:
    1. Environment override (BRAND_NAME, BRAND_EMAIL_FROM, …) — useful
       for tests + Emergent deploy panel edits without a re-commit.
    2. `<repo_root>/brand.json` (canonical).
    3. Hard-coded defaults (safety net; should never fire in prod).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

# 1. Try to load brand.json from the repo root, one level above /backend, or local backend dir.
_ROOT = Path(__file__).resolve().parent.parent
_BRAND_JSON = _ROOT / "brand.json"
if not _BRAND_JSON.exists():
    _BRAND_JSON = Path(__file__).resolve().parent / "brand.json"


_defaults: Dict[str, Any] = {
    "key": "curryandco",
    "name": "Curry & Co.",
    "legal_name": "Suparna Dey Enterprise Inc.",
    "email_from": "orders@curryandco.ca",
    "admin_email": "admin@curryandco.local",
    "support_email": "support@curryandco.ca",
    "guest_email_domain": "guest.curryandco.local",
    "delivery_admin_email": "delivery@curryandco.local",
    "region": {
        "country": "CA",
        "currency": "CAD",
        "timezone": "America/Toronto",
    },
}

_loaded: Dict[str, Any] = dict(_defaults)
if _BRAND_JSON.exists():
    try:
        with _BRAND_JSON.open("r", encoding="utf-8") as fh:
            _loaded.update(json.load(fh))
    except Exception:
        # Bad JSON — keep defaults; a rebranding fork should still boot.
        pass


def _env_or(key: str, default: Any) -> Any:
    env_key = f"BRAND_{key.upper()}"
    return os.environ.get(env_key, default)


# ---------------------------------------------------------------------------
# 2. Public accessors — import these from `server.py` etc.
BRAND_KEY:           str = _env_or("key",                 _loaded["key"])
BRAND_NAME:          str = _env_or("name",                _loaded["name"])
BRAND_LEGAL_NAME:    str = _env_or("legal_name",          _loaded["legal_name"])
BRAND_EMAIL_FROM:    str = _env_or("email_from",          _loaded["email_from"])
BRAND_ADMIN_EMAIL:   str = _env_or("admin_email",         _loaded["admin_email"])
BRAND_SUPPORT_EMAIL: str = _env_or("support_email",       _loaded["support_email"])
BRAND_GUEST_DOMAIN:  str = _env_or("guest_email_domain",  _loaded["guest_email_domain"])
BRAND_DELIVERY_EMAIL:str = _env_or("delivery_admin_email",_loaded["delivery_admin_email"])
BRAND_REGION:        Dict[str, str] = _loaded["region"]

# ---------------------------------------------------------------------------
# Central-platform (Suparna Dey) phone-home config. Empty when this tenant
# isn't registered yet — every phone-home site short-circuits in that case.
_PLATFORM: Dict[str, Any] = _loaded.get("platform") or {}
PLATFORM_TENANT_ID:  str  = os.environ.get("PLATFORM_TENANT_ID",  _PLATFORM.get("tenant_id",  "") or "")
PLATFORM_API_KEY:    str  = os.environ.get("PLATFORM_API_KEY",    _PLATFORM.get("api_key",    "") or "")
PLATFORM_STATUS_URL: str  = os.environ.get("PLATFORM_STATUS_URL", _PLATFORM.get("status_url", "") or "")
PLATFORM_POLL_SEC:   int  = int(os.environ.get("PLATFORM_POLL_SEC",
                                                _PLATFORM.get("poll_seconds", 300)))


def as_dict() -> Dict[str, Any]:
    """Return the full brand config as a dict — convenient for /api/brand endpoint."""
    return {
        "key": BRAND_KEY,
        "name": BRAND_NAME,
        "legal_name": BRAND_LEGAL_NAME,
        "email_from": BRAND_EMAIL_FROM,
        "support_email": BRAND_SUPPORT_EMAIL,
        "region": BRAND_REGION,
    }
