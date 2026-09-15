"""Curry & Co. — Phone capture, catering per-person, and admin portal tests.

Covers review-request items 1..12.
"""
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
import requests
from pymongo import MongoClient


def _load_frontend_env():
    env = Path("/app/frontend/.env")
    if env.exists():
        for line in env.read_text().splitlines():
            m = re.match(r'^\s*([A-Z0-9_]+)\s*=\s*"?([^"\s]+)"?\s*$', line)
            if m:
                os.environ.setdefault(m.group(1), m.group(2))


_load_frontend_env()
BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    os.environ.get("EXPO_BACKEND_URL", "https://curry-ecosystem.preview.emergentagent.com"),
).rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "curry_co_db")

ADMIN_EMAIL = "admin@curryandco.local"
ADMIN_PASSWORD = "curry@admin2026"


# ----------------- fixtures -----------------
@pytest.fixture(scope="session")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def mongo_db():
    c = MongoClient(MONGO_URL, serverSelectionTimeoutMS=3000)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="session", autouse=True)
def _seed(api_client):
    r = api_client.post(f"{API}/dev/seed")
    assert r.status_code == 200


@pytest.fixture()
def guest(api_client, mongo_db):
    r = api_client.post(f"{API}/auth/guest")
    assert r.status_code == 200
    data = r.json()
    yield data
    uid = data["user"]["user_id"]
    mongo_db.user_sessions.delete_many({"user_id": uid})
    mongo_db.users.delete_one({"user_id": uid})
    mongo_db.orders.delete_many({"user_id": uid})


@pytest.fixture()
def guest_headers(guest):
    return {"Authorization": f"Bearer {guest['session_token']}",
            "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def admin_token(api_client):
    r = api_client.post(f"{API}/admin/login",
                        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json"}


def _menu_item(api_client):
    r = api_client.get(f"{API}/menu/current")
    d = r.json()
    return d["items"][0]


def _order_payload(item_id, phone="6470001234", qty=2, coupon=None,
                    catering_pkg_id=None, catering_guests=None):
    if catering_pkg_id:
        items = [{"kind": "catering", "ref_id": catering_pkg_id, "quantity": 1,
                  "catering_guest_count": catering_guests}]
    else:
        items = [{"kind": "menu", "ref_id": item_id, "quantity": qty}]
    p = {
        "items": items,
        "address": {"line1": "1 King", "line2": "", "city": "Toronto",
                    "province": "ON", "postal_code": "M5V1A1"},
        "slot": {"date": "2099-01-30", "window": "friday_evening"},
        "coupon_code": coupon,
        "redeem_points": 0,
        "special_instructions": "TEST",
        "payment_method": "cod",
    }
    if phone is not None:
        p["phone"] = phone
    return p


# =========================================================
# 1. Catering seed reflects new per-person schema
# =========================================================
class TestCateringSchema:
    def test_seed_produces_per_person_packages(self, api_client):
        r = api_client.get(f"{API}/catering")
        assert r.status_code == 200
        pkgs = r.json()
        assert len(pkgs) == 3
        prices = sorted(p["price_cents"] for p in pkgs)
        assert prices == [1999, 2499, 3299]
        mins = sorted(p["min_guests"] for p in pkgs)
        assert mins == [10, 15, 30]
        for p in pkgs:
            assert "guest_count" not in p, "old field guest_count should be removed"
            assert p["min_guests"] >= 1


# =========================================================
# 2. phone REQUIRED on POST /orders
# =========================================================
class TestPhoneRequired:
    def test_missing_phone_422(self, api_client, guest_headers):
        item = _menu_item(api_client)
        payload = _order_payload(item["item_id"], phone=None)
        r = api_client.post(f"{API}/orders", json=payload, headers=guest_headers)
        assert r.status_code == 422, f"expected 422 got {r.status_code}: {r.text}"

    def test_with_phone_creates_order(self, api_client, guest_headers):
        item = _menu_item(api_client)
        payload = _order_payload(item["item_id"], phone="6479998888")
        r = api_client.post(f"{API}/orders", json=payload, headers=guest_headers)
        assert r.status_code == 200, r.text
        o = r.json()
        assert o["phone"] == "6479998888"


# =========================================================
# 3. Order phone saved to user; not overwritten later
# =========================================================
class TestPhoneSavedOnUser:
    def test_first_order_saves_phone_then_not_overwritten(self, api_client, guest_headers, guest):
        item = _menu_item(api_client)
        # first order sets phone
        p1 = _order_payload(item["item_id"], phone="6470000001")
        r1 = api_client.post(f"{API}/orders", json=p1, headers=guest_headers)
        assert r1.status_code == 200, r1.text
        me = api_client.get(f"{API}/auth/me", headers=guest_headers).json()
        assert me.get("phone") == "6470000001"

        # second order tries to set different phone; user field must stay first one
        p2 = _order_payload(item["item_id"], phone="6470000002")
        r2 = api_client.post(f"{API}/orders", json=p2, headers=guest_headers)
        assert r2.status_code == 200, r2.text
        me2 = api_client.get(f"{API}/auth/me", headers=guest_headers).json()
        assert me2.get("phone") == "6470000001", \
            f"phone must NOT be overwritten; got {me2.get('phone')}"


# =========================================================
# 4. Catering quote: per-person math + min_guests enforcement
# =========================================================
class TestCateringQuote:
    def _bengali_pkg(self, api_client):
        pkgs = api_client.get(f"{API}/catering").json()
        # per-person 1999 with min_guests 10
        matches = [p for p in pkgs if p["price_cents"] == 1999 and p["min_guests"] == 10]
        assert matches, f"Bengali Home-Style Feast not found: {pkgs}"
        return matches[0]

    def test_catering_quote_per_person_math(self, api_client, guest_headers):
        pkg = self._bengali_pkg(api_client)
        payload = _order_payload(None, phone="6470002222",
                                  catering_pkg_id=pkg["package_id"],
                                  catering_guests=20)
        r = api_client.post(f"{API}/orders/quote", json=payload, headers=guest_headers)
        assert r.status_code == 200, r.text
        q = r.json()
        # subtotal_cents should equal 1999 * 20 = 39980 (single-line, qty=1)
        assert q["subtotal_cents"] == 39980, \
            f"expected 39980 got {q['subtotal_cents']} — {q}"

    def test_catering_below_min_guests_400(self, api_client, guest_headers):
        pkg = self._bengali_pkg(api_client)
        payload = _order_payload(None, phone="6470002222",
                                  catering_pkg_id=pkg["package_id"],
                                  catering_guests=5)
        r = api_client.post(f"{API}/orders/quote", json=payload, headers=guest_headers)
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"


# =========================================================
# 6. Admin login
# =========================================================
class TestAdminLogin:
    def test_success(self, api_client):
        r = api_client.post(f"{API}/admin/login",
                            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200, r.text
        d = r.json()
        assert "access_token" in d and d["access_token"]
        assert d["admin"]["email"] == ADMIN_EMAIL

    def test_wrong_password_401(self, api_client):
        r = api_client.post(f"{API}/admin/login",
                            json={"email": ADMIN_EMAIL, "password": "wrong-password"})
        assert r.status_code == 401


# =========================================================
# 7. Admin menu CRUD gated by JWT
# =========================================================
class TestAdminMenus:
    def test_requires_auth(self, api_client):
        r = api_client.get(f"{API}/admin/menus")
        assert r.status_code == 401
        r2 = api_client.post(f"{API}/admin/menus", json={})
        assert r2.status_code in (401, 422)  # 401 preferred

    def test_menu_roundtrip(self, api_client, admin_headers, mongo_db):
        ws = "2099-01-04"
        # create week
        menu = {"week_start": ws, "title": "TEST Week 2099-01-04",
                "friday_delivery_date": "2099-01-09",
                "saturday_delivery_date": "2099-01-10", "items": [], "is_active": True}
        r = api_client.post(f"{API}/admin/menus", json=menu, headers=admin_headers)
        assert r.status_code == 200, r.text
        # add an item — wrapped payload per MenuItemUpsertReq
        item = {"item": {"name": "TEST_Item", "description": "test",
                          "price_cents": 999, "image_url": "https://x/y.jpg",
                          "category": "main", "is_veg": True}}
        ra = api_client.post(f"{API}/admin/menus/{ws}/items",
                              json=item, headers=admin_headers)
        assert ra.status_code == 200, ra.text
        added = ra.json()
        item_id = (added.get("item_id")
                   or added.get("item", {}).get("item_id")
                   or (added.get("items", [{}])[-1] or {}).get("item_id"))
        assert item_id, f"no item_id in add response: {added}"
        # list and verify
        lst = api_client.get(f"{API}/admin/menus", headers=admin_headers).json()
        week = [w for w in lst if w["week_start"] == ws]
        assert week and any(i["item_id"] == item_id for i in week[0]["items"])
        # delete item
        rd = api_client.delete(f"{API}/admin/menus/{ws}/items/{item_id}",
                                headers=admin_headers)
        assert rd.status_code == 200
        # delete week
        rw = api_client.delete(f"{API}/admin/menus/{ws}", headers=admin_headers)
        assert rw.status_code == 200
        # teardown safety
        mongo_db.weekly_menus.delete_many({"week_start": ws})


# =========================================================
# 8. Admin catering CRUD
# =========================================================
class TestAdminCatering:
    def test_roundtrip(self, api_client, admin_headers, mongo_db):
        r_pre = api_client.get(f"{API}/admin/catering", headers=admin_headers)
        assert r_pre.status_code == 200
        n_before = len(r_pre.json())

        pkg = {
            "name": "TEST_Package_xyz",
            "description": "test desc",
            "price_cents": 4999,
            "min_guests": 12,
            "image_url": "https://x/y.jpg",
            "includes": ["item a", "item b"],
            "is_featured": False,
        }
        rc = api_client.post(f"{API}/admin/catering", json=pkg, headers=admin_headers)
        assert rc.status_code == 200, rc.text
        created = rc.json()
        pid = (created.get("package_id")
               or created.get("package", {}).get("package_id")
               or created.get("pkg", {}).get("package_id"))
        assert pid, f"no package_id: {created}"

        lst = api_client.get(f"{API}/admin/catering", headers=admin_headers).json()
        assert len(lst) >= n_before + 1
        assert any(p["package_id"] == pid for p in lst)

        rd = api_client.delete(f"{API}/admin/catering/{pid}", headers=admin_headers)
        assert rd.status_code == 200
        mongo_db.catering_packages.delete_many({"package_id": pid})


# =========================================================
# 9. Admin orders list with user_summary + status filter
# =========================================================
class TestAdminOrders:
    def test_list_has_user_summary_and_filter(self, api_client, admin_headers,
                                              guest_headers):
        item = _menu_item(api_client)
        # create a COD order (immediately in "preparing")
        p = _order_payload(item["item_id"], phone="6470007777")
        rc = api_client.post(f"{API}/orders", json=p, headers=guest_headers)
        assert rc.status_code == 200, rc.text
        oid = rc.json()["order_id"]

        lst = api_client.get(f"{API}/admin/orders", headers=admin_headers)
        assert lst.status_code == 200, lst.text
        orders = lst.json()
        assert isinstance(orders, list)
        mine = [o for o in orders if o["order_id"] == oid]
        assert mine, f"created order {oid} not in admin list"
        assert "user_summary" in mine[0], mine[0].keys()
        u = mine[0]["user_summary"]
        assert "email" in u and "name" in u and "phone" in u

        # filter
        fr = api_client.get(f"{API}/admin/orders?status_filter=preparing",
                             headers=admin_headers)
        assert fr.status_code == 200
        for o in fr.json():
            assert o["status"] == "preparing"


# =========================================================
# 10. Admin order status update
# =========================================================
class TestAdminOrderStatusUpdate:
    def test_update_reflects_customer_view(self, api_client, admin_headers, guest_headers):
        item = _menu_item(api_client)
        p = _order_payload(item["item_id"], phone="6470007777")
        rc = api_client.post(f"{API}/orders", json=p, headers=guest_headers)
        oid = rc.json()["order_id"]

        ru = api_client.post(f"{API}/admin/orders/{oid}/status",
                             json={"status": "out_for_delivery",
                                   "note": "on the way"},
                             headers=admin_headers)
        assert ru.status_code == 200, ru.text

        # customer view
        rg = api_client.get(f"{API}/orders/{oid}", headers=guest_headers)
        assert rg.status_code == 200
        d = rg.json()
        assert d["status"] == "out_for_delivery"
        assert any(ev["status"] == "out_for_delivery" for ev in d["tracking_events"])


# =========================================================
# 11. Admin stats
# =========================================================
class TestAdminStats:
    def test_stats_shape(self, api_client, admin_headers):
        r = api_client.get(f"{API}/admin/stats", headers=admin_headers)
        assert r.status_code == 200, r.text
        s = r.json()
        for key in ("total_orders", "delivered", "active", "users", "revenue_cents"):
            assert key in s, f"missing {key} in stats {s}"


# =========================================================
# 12. Customer bearer must not work for admin
# =========================================================
class TestAdminAuthIsolation:
    def test_customer_token_rejected(self, api_client, guest):
        h = {"Authorization": f"Bearer {guest['session_token']}"}
        r = api_client.get(f"{API}/admin/menus", headers=h)
        assert r.status_code == 401, f"customer token must be 401 got {r.status_code}"
