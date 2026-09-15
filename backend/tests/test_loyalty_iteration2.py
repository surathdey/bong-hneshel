"""Loyalty Points feature tests (iteration 2).

Covers:
- Public /api/settings exposes loyalty_enabled/earn/redeem
- Admin can login and PUT /api/admin/settings to modify loyalty values;
  changes persist via GET /api/admin/settings and GET /api/settings.
- Admin customers list returns loyalty_points; detail returns
  {customer, orders, loyalty_history}.

IMPORTANT: The suite restores defaults (earn=1, redeem=100, enabled=true)
at teardown so downstream flows are unaffected.
"""
import os
import pytest
import requests

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "admin@bong-hneshel.ca"
ADMIN_PASSWORD = "DDuCi!dZ0UmN3vXu"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_token(api):
    r = api.post(f"{BASE_URL}/api/admin/login",
                 json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# ---------- Public /api/settings ----------
class TestPublicSettings:
    def test_public_settings_contains_loyalty_fields(self, api):
        r = api.get(f"{BASE_URL}/api/settings")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "loyalty_enabled" in data
        assert "loyalty_earn_points_per_dollar" in data
        assert "loyalty_redeem_points_per_dollar" in data
        assert isinstance(data["loyalty_enabled"], bool)
        assert isinstance(data["loyalty_earn_points_per_dollar"], int)
        assert isinstance(data["loyalty_redeem_points_per_dollar"], int)


# ---------- Admin /api/admin/settings persistence ----------
class TestAdminLoyaltySettings:
    def test_admin_can_get_settings(self, api, admin_headers):
        r = api.get(f"{BASE_URL}/api/admin/settings", headers=admin_headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "loyalty_enabled" in data
        assert "loyalty_earn_points_per_dollar" in data
        assert "loyalty_redeem_points_per_dollar" in data

    def test_put_admin_settings_persists_loyalty(self, api, admin_headers):
        # Fetch current settings, mutate loyalty fields, PUT back full doc
        cur = api.get(f"{BASE_URL}/api/admin/settings", headers=admin_headers).json()
        cur.pop("_id", None)
        cur["loyalty_enabled"] = True
        cur["loyalty_earn_points_per_dollar"] = 2
        cur["loyalty_redeem_points_per_dollar"] = 200

        r = api.put(f"{BASE_URL}/api/admin/settings", headers=admin_headers, json=cur)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        saved = body.get("settings", {})
        assert saved.get("loyalty_earn_points_per_dollar") == 2
        assert saved.get("loyalty_redeem_points_per_dollar") == 200
        assert saved.get("loyalty_enabled") is True

        # Re-fetch admin settings
        r2 = api.get(f"{BASE_URL}/api/admin/settings", headers=admin_headers).json()
        assert r2["loyalty_earn_points_per_dollar"] == 2
        assert r2["loyalty_redeem_points_per_dollar"] == 200
        assert r2["loyalty_enabled"] is True

        # Public settings reflect the new values
        pub = api.get(f"{BASE_URL}/api/settings").json()
        assert pub["loyalty_earn_points_per_dollar"] == 2
        assert pub["loyalty_redeem_points_per_dollar"] == 200
        assert pub["loyalty_enabled"] is True

    def test_zzz_restore_loyalty_defaults(self, api, admin_headers):
        """Runs last (alphabetical) — restore earn=1 redeem=100 enabled=true."""
        cur = api.get(f"{BASE_URL}/api/admin/settings", headers=admin_headers).json()
        cur.pop("_id", None)
        cur["loyalty_enabled"] = True
        cur["loyalty_earn_points_per_dollar"] = 1
        cur["loyalty_redeem_points_per_dollar"] = 100
        r = api.put(f"{BASE_URL}/api/admin/settings", headers=admin_headers, json=cur)
        assert r.status_code == 200
        pub = api.get(f"{BASE_URL}/api/settings").json()
        assert pub["loyalty_earn_points_per_dollar"] == 1
        assert pub["loyalty_redeem_points_per_dollar"] == 100
        assert pub["loyalty_enabled"] is True


# ---------- Admin customers loyalty ----------
class TestAdminCustomersLoyalty:
    def test_list_customers_has_loyalty_points_field(self, api, admin_headers):
        r = api.get(f"{BASE_URL}/api/admin/customers", headers=admin_headers)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list)
        if not rows:
            pytest.skip("No customers in DB to verify field on")
        for row in rows[:5]:
            assert "loyalty_points" in row
            assert isinstance(row["loyalty_points"], int)

    def test_customer_detail_has_loyalty_history(self, api, admin_headers):
        rows = api.get(f"{BASE_URL}/api/admin/customers", headers=admin_headers).json()
        if not rows:
            pytest.skip("No customers to fetch detail for")
        uid = rows[0]["user_id"]
        r = api.get(f"{BASE_URL}/api/admin/customers/{uid}", headers=admin_headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "customer" in data
        assert "orders" in data
        assert "loyalty_history" in data
        assert isinstance(data["orders"], list)
        assert isinstance(data["loyalty_history"], list)
        assert "loyalty_points" in data["customer"]
