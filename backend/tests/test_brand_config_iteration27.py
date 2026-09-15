"""
Iteration 27 — Brand-config refactor regression.

Verifies that the newly introduced /app/brand.json + /app/backend/brand.py
source-of-truth for tenant-specific strings does NOT change any observable
backend behaviour, and that the new public `/api/brand` endpoint returns
the expected shape used by the web-admin bundle.

Coverage:
  1. Backend imports successfully (server.py:22 imports from brand.py)
  2. GET /api/brand → 200 with { key, name, legal_name, email_from,
     support_email, region.{country,currency,timezone} }
  3. GET /api/settings still returns business_name='Curry & Co.'
  4. Admin login (admin@curryandco.local / curry@admin2026) still works
     — proves ADMIN_EMAIL default fallback via brand.py works.
  5. Guest checkout still assigns email in the `guest.curryandco.local`
     domain (regression: was hardcoded, now brand-config-driven).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import requests


# --------------------------------------------------------------- setup ---
def _load_frontend_env() -> None:
    env = Path("/app/frontend/.env")
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_frontend_env()
BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL", "")).rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@curryandco.local"
ADMIN_PASSWORD = "curry@admin2026"

BRAND_JSON = json.loads(Path("/app/brand.json").read_text())


@pytest.fixture(scope="module")
def client() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# 1) Health — backend imports without crashing
class TestServerBoots:
    def test_health_ok(self, client):
        r = client.get(f"{API}/")
        assert r.status_code == 200, r.text


# 2) /api/brand shape
class TestBrandEndpoint:
    def test_brand_endpoint_returns_expected_shape(self, client):
        r = client.get(f"{API}/brand")
        assert r.status_code == 200, r.text
        b = r.json()
        # Top-level fields
        for k in ("key", "name", "legal_name", "email_from",
                  "support_email", "region"):
            assert k in b, f"/api/brand missing key: {k}"
        # Values match brand.json (canonical source)
        assert b["key"] == BRAND_JSON["key"]
        assert b["name"] == BRAND_JSON["name"]
        assert b["legal_name"] == BRAND_JSON["legal_name"]
        assert b["email_from"] == BRAND_JSON["email_from"]
        assert b["support_email"] == BRAND_JSON["support_email"]
        # Region sub-shape
        region = b["region"]
        assert isinstance(region, dict)
        for k in ("country", "currency", "timezone"):
            assert k in region, f"region missing key: {k}"
        assert region["country"] == BRAND_JSON["region"]["country"]
        assert region["currency"] == BRAND_JSON["region"]["currency"]
        assert region["timezone"] == BRAND_JSON["region"]["timezone"]
        # Sensitive keys (admin_email, guest domain, delivery admin) MUST NOT
        # leak on the public endpoint.
        for leak in ("admin_email", "guest_email_domain",
                     "delivery_admin_email"):
            assert leak not in b, f"/api/brand leaked private key: {leak}"


# 3) /api/settings — regression: business_name still 'Curry & Co.'
class TestSettingsUnchanged:
    def test_business_name_still_curry_and_co(self, client):
        r = client.get(f"{API}/settings")
        assert r.status_code == 200, r.text
        s = r.json()
        assert s.get("business_name") == "Curry & Co.", (
            f"REGRESSION: business_name changed to {s.get('business_name')!r}"
        )
        # email defaults through brand config
        assert s.get("email") == BRAND_JSON["email_from"]
        assert s.get("currency") == BRAND_JSON["region"]["currency"]


# 4) Admin login — proves ADMIN_EMAIL fallback via brand.py
class TestAdminLoginFallback:
    def test_admin_login_still_works(self, client):
        r = client.post(f"{API}/admin/login",
                        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("token_type") == "bearer"
        assert isinstance(body.get("access_token"), str)
        assert body["access_token"].count(".") == 2  # JWT
        assert body.get("admin", {}).get("email") == ADMIN_EMAIL


# 5) Guest checkout uses brand-config-driven email domain
class TestGuestEmailDomain:
    def test_guest_email_uses_brand_guest_domain(self, client):
        r = client.post(f"{API}/auth/guest")
        assert r.status_code == 200, r.text
        j = r.json()
        assert "session_token" in j and j["session_token"].startswith("guest-")
        user = j["user"]
        expected_domain = BRAND_JSON["guest_email_domain"]
        assert user["email"].endswith(f"@{expected_domain}"), (
            f"REGRESSION: guest email {user['email']!r} does not use "
            f"brand.json guest_email_domain={expected_domain!r}"
        )
        assert user["role"] == "guest"
        assert user["user_id"].startswith("guest_")
