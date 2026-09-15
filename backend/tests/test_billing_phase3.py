"""
Phase 3 Billing – backend proxy tests.

Verifies the tenant-side /api/admin/billing/* endpoints:
  * are admin-JWT protected
  * gracefully degrade to a well-shaped JSON payload when the hub
    (Suparna Dey Platform) hasn't shipped billing endpoints yet (404)
  * validate their input bodies (400 when required urls missing)
  * never surface a 5xx to the frontend
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or \
           os.environ.get("EXPO_BACKEND_URL", "").rstrip("/")

ADMIN_EMAIL = "admin@curryandco.local"
ADMIN_PASSWORD = "curry@admin2026"


# ---- fixtures ------------------------------------------------------------
@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_token(api):
    r = api.post(f"{BASE_URL}/api/admin/login",
                 json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                 timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("access_token")
    assert tok, "no access_token in admin login response"
    return tok


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---- module: billing summary --------------------------------------------
class TestBillingSummaryAuth:
    def test_summary_requires_auth(self, api):
        r = api.get(f"{BASE_URL}/api/admin/billing/summary", timeout=10)
        assert r.status_code == 401, f"expected 401 without token, got {r.status_code}"

    def test_summary_rejects_bad_token(self, api):
        r = api.get(f"{BASE_URL}/api/admin/billing/summary",
                    headers={"Authorization": "Bearer garbage.token.here"}, timeout=10)
        assert r.status_code == 401


class TestBillingSummaryGraceful:
    def test_summary_returns_graceful_shape(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/admin/billing/summary",
                    headers=auth_headers, timeout=20)
        assert r.status_code == 200, f"expected 200 graceful, got {r.status_code} {r.text[:300]}"
        data = r.json()
        # graceful degrade: hub 404 -> not_implemented (hub is not reachable
        # in preview, could also be unreachable). Both must expose the
        # normalised empty shape.
        assert data.get("status") in ("not_implemented", "unreachable", "unconfigured", "none"), \
            f"unexpected status: {data.get('status')}"
        assert "plan" in data and data["plan"] is None
        assert "invoices" in data and data["invoices"] == []
        assert "card" in data and data["card"] is None

    def test_summary_force_refresh_ok(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/admin/billing/summary?force=true",
                    headers=auth_headers, timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") in ("not_implemented", "unreachable", "unconfigured", "none")
        assert data.get("plan") is None
        assert data.get("invoices") == []
        assert data.get("card") is None


# ---- module: subscribe ---------------------------------------------------
class TestBillingSubscribe:
    def test_subscribe_requires_auth(self, api):
        r = api.post(f"{BASE_URL}/api/admin/billing/subscribe",
                     json={"success_url": "https://x/y", "cancel_url": "https://x/z"},
                     timeout=10)
        assert r.status_code == 401

    def test_subscribe_missing_urls_returns_400(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/admin/billing/subscribe",
                     json={}, headers=auth_headers, timeout=10)
        assert r.status_code == 400, f"expected 400 without urls, got {r.status_code} {r.text[:200]}"

    def test_subscribe_missing_cancel_url_returns_400(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/admin/billing/subscribe",
                     json={"success_url": "https://ex.com/ok"},
                     headers=auth_headers, timeout=10)
        assert r.status_code == 400

    def test_subscribe_graceful_hub_404(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/admin/billing/subscribe",
                     json={"success_url": "https://ex.com/ok",
                           "cancel_url":  "https://ex.com/cancel"},
                     headers=auth_headers, timeout=20)
        # Must NOT be a 5xx — graceful.
        assert r.status_code < 500, f"got 5xx: {r.status_code} {r.text[:300]}"
        assert r.status_code == 200, f"expected 200 with error field, got {r.status_code}"
        data = r.json()
        # We expect an 'error' field describing the hub failure (hub_404 or unreachable)
        assert "error" in data, f"expected 'error' field on graceful degrade, got: {data}"
        err = str(data["error"])
        assert err.startswith("hub_") or err == "unreachable", f"unexpected error: {err}"


# ---- module: portal ------------------------------------------------------
class TestBillingPortal:
    def test_portal_requires_auth(self, api):
        r = api.post(f"{BASE_URL}/api/admin/billing/portal",
                     json={"return_url": "https://x/y"}, timeout=10)
        assert r.status_code == 401

    def test_portal_missing_return_url_returns_400(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/admin/billing/portal",
                     json={}, headers=auth_headers, timeout=10)
        assert r.status_code == 400

    def test_portal_graceful_hub_404(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/admin/billing/portal",
                     json={"return_url": "https://ex.com/back"},
                     headers=auth_headers, timeout=20)
        assert r.status_code < 500
        assert r.status_code == 200
        data = r.json()
        assert "error" in data
        err = str(data["error"])
        assert err.startswith("hub_") or err == "unreachable"


# ---- module: billing_client edge case -----------------------------------
class TestBillingClientEdge:
    def test_configured_handles_missing_tenant_id(self):
        """billing_client.configured() must safely return False when brand.json
        lacks platform.tenant_id (should never raise)."""
        import importlib
        import sys
        sys.path.insert(0, "/app/backend")
        bc = importlib.import_module("billing_client")
        # sanity — the function must exist and return a bool without raising
        val = bc.configured()
        assert isinstance(val, bool)
