"""Curry & Co. — Admin Integrations (Drive + Twilio) & Exports tests.

Covers review-request items 1..10 for iteration_18.

Uses EXPO_BACKEND_URL as BASE_URL to test through the public ingress.
"""
import os
import base64
import json
import re
from pathlib import Path

import pytest
import requests


# ---------- env / setup ----------
def _load_frontend_env():
    env = Path("/app/frontend/.env")
    if env.exists():
        for line in env.read_text().splitlines():
            m = re.match(r'^\s*([A-Z0-9_]+)\s*=\s*"?([^"\s]+)"?\s*$', line)
            if m:
                os.environ.setdefault(m.group(1), m.group(2))


_load_frontend_env()
BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ["EXPO_BACKEND_URL"]).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@curryandco.local"
ADMIN_PASSWORD = "curry@admin2026"

FAKE_SA_JSON = json.dumps({
    "type": "service_account",
    "client_email": "test@fake.iam.gserviceaccount.com",
    "private_key": "-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----",
    "token_uri": "https://oauth2.googleapis.com/token",
})


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session", autouse=True)
def _seed(api_client):
    # Ensure DB is seeded so we have some customers/orders for aggregation tests.
    r = api_client.post(f"{API}/dev/seed")
    assert r.status_code == 200, r.text


@pytest.fixture(scope="session")
def admin_token(api_client):
    r = api_client.post(f"{API}/admin/login",
                        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data and "admin" in data
    return data["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def guest_session(api_client):
    """Create a guest session then place a COD order so we have a customer with
    orders — used for the customers aggregation tests."""
    r = api_client.post(f"{API}/auth/guest")
    assert r.status_code == 200
    data = r.json()
    tok = data["session_token"]
    uid = data["user"]["user_id"]
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    # Pick a menu item
    m = api_client.get(f"{API}/menu/current").json()
    if m and m.get("items"):
        it = m["items"][0]
        order_body = {
            "items": [{"kind": "menu", "ref_id": it["item_id"], "quantity": 1}],
            "address": {"line1": "123 Test St", "city": "Toronto",
                        "province": "ON", "postal_code": "M5V 2T6"},
            "slot": {"date": "2026-01-31", "window": "saturday_morning"},
            "phone": "+14165550000",
            "payment_method": "cod",
        }
        r2 = api_client.post(f"{API}/orders", headers=h, json=order_body)
        # Non-fatal — if it fails, tests dependent on this can skip.
    return {"user_id": uid, "token": tok}


# =====================================================================
# 1) GET /api/admin/integrations
# =====================================================================
class TestIntegrationsGet:
    def test_requires_auth(self, api_client):
        r = api_client.get(f"{API}/admin/integrations")
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_crypto_ready_true(self, api_client, admin_headers):
        r = api_client.get(f"{API}/admin/integrations", headers=admin_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["crypto_ready"] is True, "INTEGRATIONS_FERNET_KEY should be set"
        assert "google_drive" in d and "twilio" in d
        assert "configured" in d["google_drive"]
        assert "configured" in d["twilio"]


# =====================================================================
# 2) PUT /api/admin/integrations/google-drive
# =====================================================================
class TestDriveSettings:
    def test_invalid_json_returns_400(self, api_client, admin_headers):
        body = {
            "service_account_json": "not-valid-json",
            "folder_id": "test-folder-id",
            "user_email": "you@test.com",
        }
        r = api_client.put(f"{API}/admin/integrations/google-drive",
                           headers=admin_headers, json=body)
        assert r.status_code == 400, r.text
        assert "Invalid service-account JSON" in r.text

    def test_valid_shape_json_returns_200(self, api_client, admin_headers):
        body = {
            "service_account_json": FAKE_SA_JSON,
            "folder_id": "test-folder-id",
            "user_email": "you@test.com",
        }
        r = api_client.put(f"{API}/admin/integrations/google-drive",
                           headers=admin_headers, json=body)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

    def test_get_reflects_configured_and_no_ciphertext(self, api_client, admin_headers):
        r = api_client.get(f"{API}/admin/integrations", headers=admin_headers)
        assert r.status_code == 200
        gd = r.json()["google_drive"]
        assert gd["configured"] is True
        assert gd["folder_id"] == "test-folder-id"
        assert gd["user_email"] == "you@test.com"
        assert gd["client_email"] == "test@fake.iam.gserviceaccount.com"
        # Encrypted JSON must never leak in the response
        assert "service_account_json_encrypted" not in json.dumps(r.json())
        assert "BEGIN PRIVATE KEY" not in json.dumps(r.json())


# =====================================================================
# 3) POST /api/admin/integrations/google-drive/test
# =====================================================================
class TestDriveConnectivity:
    def test_fake_creds_return_4xx_not_500(self, api_client, admin_headers):
        r = api_client.post(f"{API}/admin/integrations/google-drive/test",
                            headers=admin_headers)
        assert 400 <= r.status_code < 500, f"expected 4xx, got {r.status_code}: {r.text}"
        # must be JSON with detail
        assert r.headers.get("content-type", "").startswith("application/json")
        assert "detail" in r.json()


# =====================================================================
# 4) PUT /api/admin/integrations/twilio
# =====================================================================
class TestTwilioSettings:
    def test_save_ok(self, api_client, admin_headers):
        r = api_client.put(f"{API}/admin/integrations/twilio",
                           headers=admin_headers,
                           json={"account_sid": "ACfake123",
                                 "auth_token": "fake-token",
                                 "from_number": "+14165551234"})
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

    def test_get_reflects_and_no_secret(self, api_client, admin_headers):
        r = api_client.get(f"{API}/admin/integrations", headers=admin_headers)
        assert r.status_code == 200
        tw = r.json()["twilio"]
        assert tw["configured"] is True
        assert tw["account_sid"] == "ACfake123"
        assert tw["from_number"] == "+14165551234"
        blob = json.dumps(r.json())
        assert "fake-token" not in blob
        assert "auth_token_encrypted" not in blob


# =====================================================================
# 5) POST /api/admin/integrations/twilio/test
# =====================================================================
class TestTwilioConnectivity:
    def test_fake_creds_return_4xx_not_500(self, api_client, admin_headers):
        r = api_client.post(f"{API}/admin/integrations/twilio/test",
                            headers=admin_headers,
                            json={"to_number": "+14165551234"})
        assert 400 <= r.status_code < 500, f"expected 4xx, got {r.status_code}: {r.text}"
        assert r.headers.get("content-type", "").startswith("application/json")
        j = r.json()
        assert "detail" in j
        assert isinstance(j["detail"], str) and len(j["detail"]) > 0


# =====================================================================
# 6) GET /api/admin/customers
# =====================================================================
class TestCustomersList:
    def test_returns_summaries(self, api_client, admin_headers, guest_session):
        r = api_client.get(f"{API}/admin/customers", headers=admin_headers)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list)
        assert len(rows) > 0
        required = {"user_id", "name", "email", "phone", "role", "created_at",
                    "loyalty_points", "total_orders", "total_spent_cents",
                    "last_order_date", "last_order_status", "addresses"}
        assert required.issubset(set(rows[0].keys())), \
            f"missing fields: {required - set(rows[0].keys())}"

    def test_at_least_one_customer_has_orders(self, api_client, admin_headers, guest_session):
        r = api_client.get(f"{API}/admin/customers", headers=admin_headers)
        rows = r.json()
        with_orders = [r for r in rows if r["total_orders"] > 0]
        assert len(with_orders) > 0, "expected at least one customer with orders"
        c = with_orders[0]
        assert c["total_spent_cents"] > 0

    def test_query_filter_guest(self, api_client, admin_headers, guest_session):
        r = api_client.get(f"{API}/admin/customers", headers=admin_headers,
                           params={"q": "guest"})
        assert r.status_code == 200, r.text
        rows = r.json()
        # All returned rows should contain "guest" in name/email/phone
        for row in rows:
            hay = f"{row['name']} {row['email']} {row['phone']}".lower()
            assert "guest" in hay, f"row does not match guest filter: {row}"


# =====================================================================
# 7) GET /api/admin/customers/{user_id}
# =====================================================================
class TestCustomerDetail:
    def test_detail_ok(self, api_client, admin_headers, guest_session):
        list_r = api_client.get(f"{API}/admin/customers", headers=admin_headers)
        rows = list_r.json()
        target = next((r for r in rows if r["total_orders"] > 0), None)
        assert target is not None, "no customer with orders found for detail test"
        uid = target["user_id"]
        r = api_client.get(f"{API}/admin/customers/{uid}", headers=admin_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "customer" in d and "orders" in d
        assert d["customer"]["user_id"] == uid
        assert isinstance(d["orders"], list)

    def test_detail_bogus_404(self, api_client, admin_headers):
        r = api_client.get(f"{API}/admin/customers/user_nonexistent_123",
                           headers=admin_headers)
        assert r.status_code == 404, r.text


# =====================================================================
# 8) POST /api/admin/orders/export
# =====================================================================
class TestOrdersExport:
    def test_download_all(self, api_client, admin_headers, guest_session):
        r = api_client.post(f"{API}/admin/orders/export", headers=admin_headers,
                            json={"order_ids": [], "destination": "download"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["kind"] == "download"
        assert d["filename"].endswith(".xlsx")
        assert d["content_type"].startswith("application/vnd.openxmlformats")
        raw = base64.b64decode(d["b64"])
        assert raw[:2] == b"PK", "XLSX should start with ZIP magic PK"
        assert d["count"] > 0

    def test_nonexistent_ids_400(self, api_client, admin_headers):
        r = api_client.post(f"{API}/admin/orders/export", headers=admin_headers,
                            json={"order_ids": ["nonexistent-id"], "destination": "download"})
        assert r.status_code == 400, r.text
        assert "No orders match" in r.text

    def test_drive_destination_no_500(self, api_client, admin_headers):
        # Since drive creds are fake, upload will fail — should be 4xx, not 500.
        r = api_client.post(f"{API}/admin/orders/export", headers=admin_headers,
                            json={"order_ids": [], "destination": "drive"})
        assert 400 <= r.status_code < 500, f"expected 4xx got {r.status_code}: {r.text}"
        assert "detail" in r.json()

    def test_sms_destination_no_500(self, api_client, admin_headers):
        r = api_client.post(f"{API}/admin/orders/export", headers=admin_headers,
                            json={"order_ids": [], "destination": "sms",
                                  "sms_to": "+14165551234"})
        assert 400 <= r.status_code < 500, f"expected 4xx got {r.status_code}: {r.text}"
        assert "detail" in r.json()


# =====================================================================
# 9) POST /api/admin/customers/export
# =====================================================================
class TestCustomersExport:
    def test_download_with_history(self, api_client, admin_headers, guest_session):
        r = api_client.post(f"{API}/admin/customers/export", headers=admin_headers,
                            json={"user_ids": [], "destination": "download",
                                  "include_order_history": True})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["kind"] == "download"
        raw = base64.b64decode(d["b64"])
        assert raw[:2] == b"PK"
        assert d["count"] > 0

    def test_download_without_history(self, api_client, admin_headers, guest_session):
        r = api_client.post(f"{API}/admin/customers/export", headers=admin_headers,
                            json={"user_ids": [], "destination": "download",
                                  "include_order_history": False})
        assert r.status_code == 200, r.text
        d = r.json()
        raw = base64.b64decode(d["b64"])
        assert raw[:2] == b"PK"
        assert d["count"] > 0


# =====================================================================
# 10) Authorization — endpoints reject requests without bearer
# =====================================================================
class TestAuthorizationRequired:
    def test_customers_no_auth(self, api_client):
        r = api_client.get(f"{API}/admin/customers")
        assert r.status_code in (401, 403)

    def test_integrations_no_auth(self, api_client):
        r = api_client.get(f"{API}/admin/integrations")
        assert r.status_code in (401, 403)

    def test_orders_export_no_auth(self, api_client):
        r = api_client.post(f"{API}/admin/orders/export",
                            json={"order_ids": [], "destination": "download"})
        assert r.status_code in (401, 403)

    def test_drive_test_no_auth(self, api_client):
        r = api_client.post(f"{API}/admin/integrations/google-drive/test")
        assert r.status_code in (401, 403)
