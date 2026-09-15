"""
Backend tests for Weekly Menu Package (v3): à la carte + package mode toggles.
Covers:
  - /api/dev/seed idempotency (preserves admin toggles/package)
  - /api/menu/current includes new fields
  - /api/admin/menus/{week_start}/settings validation and upserts
  - /api/orders/quote & /api/orders with kind=weekly_package
  - Existing catering v2 quote still passes (regression sanity)
"""
import os
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL", "")).rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@curryandco.local"
ADMIN_PASSWORD = "curry@admin2026"


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def seeded(client):
    r = client.post(f"{API}/dev/seed", timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def admin_token(client, seeded):
    r = client.post(f"{API}/admin/login",
                    json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_hdr(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module", autouse=True)
def _reset_toggles(client, admin_hdr):
    """Ensure current week's package is enabled with the demo config before tests run."""
    m = client.get(f"{API}/menu/current").json()
    ws = m["week_start"]
    demo = {
        "name": "This Week's Combo",
        "description": "Build your own mini-thali — pick 3 dishes from this week's menu and save.",
        "price_cents": 3499,
        "pick_count": 3,
        "eligible_master_ids": [],
        "image_url": "",
    }
    client.post(f"{API}/admin/menus/{ws}/settings",
                json={"alacarte_enabled": True, "package_enabled": True, "package": demo},
                headers=admin_hdr)
    yield


@pytest.fixture(scope="module")
def guest_token(client):
    r = client.post(f"{API}/auth/guest")
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


@pytest.fixture(scope="module")
def guest_hdr(guest_token):
    return {"Authorization": f"Bearer {guest_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="function")
def current_menu(client, seeded):
    r = client.get(f"{API}/menu/current")
    assert r.status_code == 200, r.text
    m = r.json()
    assert m is not None
    return m


# ---------- 1. Seed & /menu/current fields ----------
class TestSeedAndCurrentMenu:
    def test_current_menu_has_toggles_and_package(self, current_menu):
        assert "alacarte_enabled" in current_menu
        assert "package_enabled" in current_menu
        assert current_menu["alacarte_enabled"] is True
        assert current_menu["package_enabled"] is True
        pkg = current_menu.get("package")
        assert pkg is not None, "current menu must include a package"
        assert pkg["name"] == "This Week's Combo"
        assert pkg["pick_count"] == 3
        assert pkg["price_cents"] == 3499
        assert pkg.get("eligible_master_ids") == []

    def test_future_weeks_have_package_disabled(self, client):
        r = client.get(f"{API}/menu/upcoming")
        assert r.status_code == 200
        arr = r.json()
        assert len(arr) >= 1
        for wm in arr:
            assert wm.get("package_enabled") is False, \
                f"future week {wm['week_start']} should have package disabled by default"


# ---------- 2. Admin settings endpoint ----------
class TestAdminSettings:
    def test_reject_both_toggles_off(self, client, admin_hdr, current_menu):
        ws = current_menu["week_start"]
        # try to disable a la carte while ensuring package is also false
        # First flip package off legitimately (a la carte still true)
        r0 = client.post(f"{API}/admin/menus/{ws}/settings",
                         json={"package_enabled": False}, headers=admin_hdr)
        assert r0.status_code == 200, r0.text
        # Now try to disable a la carte too -> should 400
        r1 = client.post(f"{API}/admin/menus/{ws}/settings",
                         json={"alacarte_enabled": False}, headers=admin_hdr)
        assert r1.status_code == 400
        assert "at least one" in r1.text.lower()
        # restore: re-enable package for downstream tests
        r2 = client.post(f"{API}/admin/menus/{ws}/settings",
                         json={"package_enabled": True}, headers=admin_hdr)
        assert r2.status_code == 200

    def test_upsert_package_via_settings(self, client, admin_hdr, current_menu):
        ws = current_menu["week_start"]
        new_pkg = {
            "name": "TEST_Combo",
            "description": "Test pick 2 combo",
            "price_cents": 2999,
            "pick_count": 2,
            "eligible_master_ids": [],
            "image_url": "",
        }
        r = client.post(f"{API}/admin/menus/{ws}/settings",
                        json={"package": new_pkg, "package_enabled": True},
                        headers=admin_hdr)
        assert r.status_code == 200, r.text
        menu = r.json()["menu"]
        assert menu["package"]["name"] == "TEST_Combo"
        assert menu["package"]["pick_count"] == 2
        # Restore original demo package
        restore = {
            "name": "This Week's Combo",
            "description": "Build your own mini-thali — pick 3 dishes from this week's menu and save.",
            "price_cents": 3499,
            "pick_count": 3,
            "eligible_master_ids": [],
            "image_url": "",
        }
        rr = client.post(f"{API}/admin/menus/{ws}/settings",
                         json={"package": restore, "package_enabled": True,
                               "alacarte_enabled": True},
                         headers=admin_hdr)
        assert rr.status_code == 200


# ---------- 3. Seed idempotency ----------
class TestSeedIdempotency:
    def test_seed_preserves_admin_edits(self, client, admin_hdr, current_menu):
        ws = current_menu["week_start"]
        # Turn package off via admin
        r1 = client.post(f"{API}/admin/menus/{ws}/settings",
                         json={"package_enabled": False}, headers=admin_hdr)
        assert r1.status_code == 200
        # Re-run seed
        r2 = client.post(f"{API}/dev/seed", timeout=60)
        assert r2.status_code == 200
        # Verify still off
        m = client.get(f"{API}/menu/current").json()
        assert m["package_enabled"] is False, "seed must preserve admin-set package_enabled=false"
        # Restore
        r3 = client.post(f"{API}/admin/menus/{ws}/settings",
                         json={"package_enabled": True}, headers=admin_hdr)
        assert r3.status_code == 200
        m2 = client.get(f"{API}/menu/current").json()
        assert m2["package_enabled"] is True


# ---------- 4. Weekly package quote/order ----------
def _addr():
    return {"line1": "1 Bay St", "city": "Toronto", "province": "ON", "postal_code": "M5H2N2"}


def _slot():
    return {"date": "2026-01-30", "window": "friday_evening"}


class TestWeeklyPackageOrders:
    def test_quote_success(self, client, guest_hdr, current_menu):
        menu_id = current_menu["menu_id"]
        item_ids = [it["item_id"] for it in current_menu["items"]][:3]
        assert len(item_ids) == 3
        body = {
            "items": [{"kind": "weekly_package", "ref_id": menu_id,
                       "quantity": 1, "package_selections": item_ids}],
            "address": _addr(), "slot": _slot(),
        }
        r = client.post(f"{API}/orders/quote", json=body, headers=guest_hdr)
        assert r.status_code == 200, r.text
        q = r.json()
        assert q["subtotal_cents"] == 3499
        snap = q["items_snapshot"][0]
        assert snap["kind"] == "weekly_package"
        assert snap["line_total_cents"] == 3499
        assert snap["package_selection_ids"] == item_ids
        assert len(snap["package_selection_names"]) == 3
        assert snap["weekly_menu_id"] == menu_id

    def test_quote_wrong_pick_count(self, client, guest_hdr, current_menu):
        menu_id = current_menu["menu_id"]
        item_ids = [it["item_id"] for it in current_menu["items"]][:2]
        body = {
            "items": [{"kind": "weekly_package", "ref_id": menu_id,
                       "quantity": 1, "package_selections": item_ids}],
            "address": _addr(), "slot": _slot(),
        }
        r = client.post(f"{API}/orders/quote", json=body, headers=guest_hdr)
        assert r.status_code == 400
        assert "3 items" in r.text or "exactly" in r.text.lower()

    def test_quote_ineligible_item(self, client, guest_hdr, current_menu):
        menu_id = current_menu["menu_id"]
        item_ids = [it["item_id"] for it in current_menu["items"]][:2]
        body = {
            "items": [{"kind": "weekly_package", "ref_id": menu_id,
                       "quantity": 1,
                       "package_selections": item_ids + ["mi_notreal9999"]}],
            "address": _addr(), "slot": _slot(),
        }
        r = client.post(f"{API}/orders/quote", json=body, headers=guest_hdr)
        assert r.status_code == 400
        assert "eligible" in r.text.lower()

    def test_quote_rejected_when_package_disabled(self, client, guest_hdr, admin_hdr, current_menu):
        menu_id = current_menu["menu_id"]
        ws = current_menu["week_start"]
        item_ids = [it["item_id"] for it in current_menu["items"]][:3]
        # disable package
        r0 = client.post(f"{API}/admin/menus/{ws}/settings",
                         json={"package_enabled": False}, headers=admin_hdr)
        assert r0.status_code == 200
        body = {
            "items": [{"kind": "weekly_package", "ref_id": menu_id,
                       "quantity": 1, "package_selections": item_ids}],
            "address": _addr(), "slot": _slot(),
        }
        r = client.post(f"{API}/orders/quote", json=body, headers=guest_hdr)
        assert r.status_code == 400
        assert "not enabled" in r.text.lower()
        # re-enable
        client.post(f"{API}/admin/menus/{ws}/settings",
                    json={"package_enabled": True}, headers=admin_hdr)

    def test_order_create_flat_price_qty2(self, client, guest_hdr, current_menu):
        menu_id = current_menu["menu_id"]
        item_ids = [it["item_id"] for it in current_menu["items"]][:3]
        body = {
            "items": [{"kind": "weekly_package", "ref_id": menu_id,
                       "quantity": 2, "package_selections": item_ids}],
            "address": _addr(), "slot": _slot(),
            "phone": "4165551234", "payment_method": "cod",
        }
        r = client.post(f"{API}/orders", json=body, headers=guest_hdr)
        assert r.status_code == 200, r.text
        o = r.json()
        assert o["subtotal_cents"] == 3499 * 2
        snap = o["items_snapshot"][0]
        assert snap["line_total_cents"] == 3499 * 2
        assert snap["package_selection_ids"] == item_ids
        assert "package_selection_names" in snap
        assert snap["weekly_menu_id"] == menu_id
        assert o["order_id"].startswith("ord_")


# ---------- 5. Regression: catering v2 still works ----------
class TestCateringRegression:
    def test_catering_list_ok(self, client):
        r = client.get(f"{API}/catering")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert len(r.json()) >= 1
