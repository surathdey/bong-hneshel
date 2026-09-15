"""
Backend tests for the per-payment-method HST / config feature (Wave 4k).

Covers:
- Admin CRUD of `payment_methods` via /admin/settings (PUT).
- Public /api/settings exposes safe fields only (no secret_key / client_secret).
- /api/orders/quote respects per-method tax_enabled.
- /api/orders with payment_method="interac" creates confirmed order with interac_pending
  and tracking event mentioning "Interac".
"""
import os
import re
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
import requests
from pymongo import MongoClient


# --- Env & constants ---------------------------------------------------------
def _load_frontend_env():
    env = Path("/app/frontend/.env")
    if env.exists():
        for line in env.read_text().splitlines():
            m = re.match(r'^\s*([A-Z0-9_]+)\s*=\s*"?([^"\s]+)"?\s*$', line)
            if m:
                os.environ.setdefault(m.group(1), m.group(2))


_load_frontend_env()
BASE_URL = (
    os.environ.get("EXPO_BACKEND_URL")
    or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
).rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "curry_co_db")

ADMIN_EMAIL = "admin@curryandco.local"
ADMIN_PASSWORD = "curry@admin2026"


# --- Fixtures ----------------------------------------------------------------
@pytest.fixture(scope="module")
def mongo_db():
    c = MongoClient(MONGO_URL, serverSelectionTimeoutMS=3000)
    yield c[DB_NAME]
    c.close()


@pytest.fixture
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module", autouse=True)
def _seed():
    with requests.Session() as s:
        s.post(f"{API}/dev/seed")


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/admin/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def original_settings(admin_headers, mongo_db):
    r = requests.get(f"{API}/admin/settings", headers=admin_headers)
    assert r.status_code == 200
    orig = r.json()
    yield orig
    # Restore original after all tests
    orig_clean = {k: v for k, v in orig.items() if k != "_id"}
    mongo_db.business_settings.update_one(
        {"key": "default"}, {"$set": orig_clean}, upsert=True
    )


@pytest.fixture
def guest(api_client, mongo_db):
    r = api_client.post(f"{API}/auth/guest")
    assert r.status_code == 200
    data = r.json()
    yield data
    uid = data["user"]["user_id"]
    mongo_db.user_sessions.delete_many({"user_id": uid})
    mongo_db.users.delete_one({"user_id": uid})
    mongo_db.orders.delete_many({"user_id": uid})


def _headers(guest):
    return {"Authorization": f"Bearer {guest['session_token']}",
            "Content-Type": "application/json"}


def _this_week_friday_iso():
    today = datetime.now(timezone.utc).date()
    days_since_sun = (today.weekday() + 1) % 7
    sunday = today - timedelta(days=days_since_sun)
    return (sunday + timedelta(days=5)).isoformat()


def _menu_item(api_client):
    r = api_client.get(f"{API}/menu/current")
    assert r.status_code == 200
    it = r.json()["items"][0]
    return it["item_id"], it["price_cents"]


def _order_payload(item_id, qty=2, pm="card"):
    return {
        "items": [{"kind": "menu", "ref_id": item_id, "quantity": qty}],
        "address": {"line1": "1 King St W", "line2": "", "city": "Toronto",
                    "province": "ON", "postal_code": "M5H1A1"},
        "slot": {"date": _this_week_friday_iso(), "window": "friday_evening"},
        "phone": "6479991111",
        "coupon_code": None,
        "redeem_points": 0,
        "special_instructions": "TEST_payment_methods",
        "payment_method": pm,
    }


# =============================================================================
# 1. Admin: payment_methods CRUD through /admin/settings
# =============================================================================
class TestAdminPaymentMethodsCRUD:
    """Admin can update all four methods (enabled + tax_enabled + keys/email/notes)."""

    def _payload_with_methods(self, base_settings):
        s = deepcopy(base_settings)
        s.pop("_id", None)
        s["payment_methods"] = {
            "stripe":  {"enabled": True,  "tax_enabled": True,
                        "publishable_key": "pk_test_ADMIN_123",
                        "secret_key":      "sk_test_ADMIN_456"},
            "paypal":  {"enabled": True,  "tax_enabled": True,
                        "client_id":     "pp_client_ADMIN",
                        "client_secret": "pp_secret_ADMIN"},
            "cod":     {"enabled": True,  "tax_enabled": False},
            "interac": {"enabled": True,  "tax_enabled": True,
                        "email":        "interac-admin@curryandco.ca",
                        "instructions": "TEST Interac note pattern"},
        }
        return s

    def test_admin_login_and_get_settings(self, admin_headers):
        r = requests.get(f"{API}/admin/settings", headers=admin_headers)
        assert r.status_code == 200
        j = r.json()
        assert "payment_methods" in j

    def test_admin_put_all_four_methods(self, admin_headers, original_settings):
        payload = self._payload_with_methods(original_settings)
        r = requests.put(f"{API}/admin/settings",
                         json=payload, headers=admin_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        pm = body["settings"]["payment_methods"]
        assert pm["stripe"]["enabled"] is True
        assert pm["stripe"]["publishable_key"] == "pk_test_ADMIN_123"
        assert pm["stripe"]["secret_key"] == "sk_test_ADMIN_456"
        assert pm["paypal"]["client_id"] == "pp_client_ADMIN"
        assert pm["paypal"]["client_secret"] == "pp_secret_ADMIN"
        assert pm["cod"]["tax_enabled"] is False
        assert pm["interac"]["enabled"] is True
        assert pm["interac"]["email"] == "interac-admin@curryandco.ca"

    def test_admin_get_echoes_stored_values(self, admin_headers):
        r = requests.get(f"{API}/admin/settings", headers=admin_headers)
        assert r.status_code == 200
        pm = r.json()["payment_methods"]
        assert pm["stripe"]["secret_key"] == "sk_test_ADMIN_456"
        assert pm["paypal"]["client_secret"] == "pp_secret_ADMIN"
        assert pm["cod"]["tax_enabled"] is False
        assert pm["interac"]["email"] == "interac-admin@curryandco.ca"
        assert pm["interac"]["instructions"] == "TEST Interac note pattern"


# =============================================================================
# 2. Public /api/settings sanitization (never expose secrets)
# =============================================================================
class TestPublicSettingsSanitization:
    def test_public_settings_exposes_safe_fields_only(self):
        r = requests.get(f"{API}/settings")
        assert r.status_code == 200
        j = r.json()
        assert "payment_methods" in j
        pm = j["payment_methods"]
        for method in ("stripe", "paypal", "cod", "interac"):
            assert method in pm, f"missing {method}"
            assert "secret_key" not in pm[method], f"{method} leaks secret_key!"
            assert "client_secret" not in pm[method], f"{method} leaks client_secret!"
        # Publishable identifiers ARE safe and must be present for stripe & paypal
        assert "publishable_key" in pm["stripe"]
        assert pm["stripe"]["publishable_key"] == "pk_test_ADMIN_123"
        assert "client_id" in pm["paypal"]
        assert pm["paypal"]["client_id"] == "pp_client_ADMIN"
        # Interac email + instructions must be visible to customer
        assert pm["interac"]["email"] == "interac-admin@curryandco.ca"
        assert pm["interac"]["instructions"] == "TEST Interac note pattern"
        # Every method should have enabled + tax_enabled
        for method in ("stripe", "paypal", "cod", "interac"):
            assert isinstance(pm[method]["enabled"], bool)
            assert isinstance(pm[method]["tax_enabled"], bool)


# =============================================================================
# 3. /orders/quote applies per-method tax_enabled
# =============================================================================
class TestQuotePerMethodTax:
    """With cod.tax_enabled=False and stripe/interac/paypal tax_enabled=True."""

    def test_quote_card_has_tax(self, api_client, guest):
        item_id, _ = _menu_item(api_client)
        r = api_client.post(f"{API}/orders/quote",
                            json=_order_payload(item_id, pm="card"),
                            headers=_headers(guest))
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["tax_enabled"] is True
        assert j["tax_cents"] > 0

    def test_quote_cod_has_no_tax(self, api_client, guest):
        item_id, _ = _menu_item(api_client)
        r = api_client.post(f"{API}/orders/quote",
                            json=_order_payload(item_id, pm="cod"),
                            headers=_headers(guest))
        assert r.status_code == 200
        j = r.json()
        assert j["tax_enabled"] is False
        assert j["tax_cents"] == 0

    def test_quote_interac_has_tax(self, api_client, guest):
        item_id, _ = _menu_item(api_client)
        r = api_client.post(f"{API}/orders/quote",
                            json=_order_payload(item_id, pm="interac"),
                            headers=_headers(guest))
        assert r.status_code == 200
        j = r.json()
        assert j["tax_enabled"] is True
        assert j["tax_cents"] > 0

    def test_quote_paypal_has_tax(self, api_client, guest):
        item_id, _ = _menu_item(api_client)
        r = api_client.post(f"{API}/orders/quote",
                            json=_order_payload(item_id, pm="paypal"),
                            headers=_headers(guest))
        assert r.status_code == 200
        j = r.json()
        assert j["tax_enabled"] is True
        assert j["tax_cents"] > 0


# =============================================================================
# 4. Interac order creation
# =============================================================================
class TestInteracOrderCreation:
    def test_interac_order_confirmed_and_tracked(self, api_client, guest):
        item_id, _ = _menu_item(api_client)
        r = api_client.post(f"{API}/orders",
                            json=_order_payload(item_id, qty=2, pm="interac"),
                            headers=_headers(guest))
        assert r.status_code == 200, r.text
        o = r.json()
        assert o["payment_method"] == "interac"
        assert o["status"] == "confirmed"
        assert o["payment_status"] == "interac_pending"
        # tracking must include a confirmed event mentioning Interac
        events = o["tracking_events"]
        statuses = [e["status"] for e in events]
        assert "new" in statuses and "confirmed" in statuses
        confirmed_note = next(e["note"] for e in events if e["status"] == "confirmed")
        assert "interac" in confirmed_note.lower(), (
            f"confirmed note doesn't mention Interac: {confirmed_note}"
        )
        # tax_cents > 0 because interac.tax_enabled=True in fixture
        assert o["tax_cents"] > 0
        # Loyalty points awarded like COD
        assert o["points_awarded"] == o["subtotal_cents"] // 100

    def test_interac_order_shows_in_orders_list(self, api_client, guest):
        item_id, _ = _menu_item(api_client)
        r = api_client.post(f"{API}/orders",
                            json=_order_payload(item_id, pm="interac"),
                            headers=_headers(guest))
        assert r.status_code == 200
        oid = r.json()["order_id"]
        rl = api_client.get(f"{API}/orders", headers=_headers(guest))
        assert rl.status_code == 200
        assert oid in [o["order_id"] for o in rl.json()]


# =============================================================================
# 5. Disabled method still allowed at backend layer (defensive) — documenting
# =============================================================================
class TestDisabledMethodBehavior:
    """Backend doesn't hard-block a disabled method (frontend hides it).
    Just document that quote still works — frontend is the gatekeeper for UX."""

    def test_disabled_method_quote_still_works(self, api_client, guest, admin_headers,
                                               original_settings, mongo_db):
        # Temporarily disable paypal
        s = deepcopy(original_settings)
        s.pop("_id", None)
        s["payment_methods"] = deepcopy(s.get("payment_methods") or {})
        s["payment_methods"]["paypal"] = {
            "enabled": False, "tax_enabled": True,
            "client_id": "pp_client_ADMIN", "client_secret": "pp_secret_ADMIN",
        }
        # Restore other test-modified fields:
        s["payment_methods"]["stripe"] = {
            "enabled": True, "tax_enabled": True,
            "publishable_key": "pk_test_ADMIN_123",
            "secret_key": "sk_test_ADMIN_456",
        }
        s["payment_methods"]["cod"] = {"enabled": True, "tax_enabled": False}
        s["payment_methods"]["interac"] = {
            "enabled": True, "tax_enabled": True,
            "email": "interac-admin@curryandco.ca",
            "instructions": "TEST Interac note pattern",
        }
        rp = requests.put(f"{API}/admin/settings", json=s, headers=admin_headers)
        assert rp.status_code == 200

        item_id, _ = _menu_item(api_client)
        r = api_client.post(f"{API}/orders/quote",
                            json=_order_payload(item_id, pm="paypal"),
                            headers=_headers(guest))
        # Should still respond with 200 (backend doesn't hard-block)
        assert r.status_code == 200
