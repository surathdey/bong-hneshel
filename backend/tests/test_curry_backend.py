"""Curry & Co. backend API tests.

Runs against the public preview URL from frontend/.env (EXPO_BACKEND_URL).
Covers health, seed, menu, catering, coupons, auth-gated orders/quote/checkout,
delivery-partner apply, register-push.
"""
import os
import re
import time
import uuid
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

import pytest
import requests
from pymongo import MongoClient


# ------- Resolve BASE_URL from frontend/.env EXPO_BACKEND_URL -------
def _load_frontend_env():
    env = Path("/app/frontend/.env")
    if env.exists():
        for line in env.read_text().splitlines():
            m = re.match(r'^\s*([A-Z0-9_]+)\s*=\s*"?([^"\s]+)"?\s*$', line)
            if m:
                os.environ.setdefault(m.group(1), m.group(2))


_load_frontend_env()
BASE_URL = os.environ.get(
    "EXPO_BACKEND_URL",
    "https://curry-ecosystem.preview.emergentagent.com",
).rstrip("/")
assert BASE_URL, "EXPO_BACKEND_URL required"
API = f"{BASE_URL}/api"

# ------- Direct Mongo for synthetic session insertion -------
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "curry_co_db")


@pytest.fixture(scope="session")
def mongo_db():
    c = MongoClient(MONGO_URL, serverSelectionTimeoutMS=3000)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="session")
def session_token(mongo_db):
    """Insert synthetic user + session and return bearer token."""
    token = f"test_token_{uuid.uuid4().hex[:8]}"
    user_id = f"user_test_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    mongo_db.users.insert_one({
        "user_id": user_id,
        "email": f"TEST_{user_id}@curry.co",
        "name": "TEST User",
        "picture": None,
        "phone": None,
        "default_address": None,
        "loyalty_points": 0,
        "created_at": now,
        "role": "customer",
    })
    mongo_db.user_sessions.insert_one({
        "session_token": token,
        "user_id": user_id,
        "created_at": now,
        "expires_at": now + timedelta(days=7),
    })
    yield {"token": token, "user_id": user_id}
    # teardown
    mongo_db.user_sessions.delete_one({"session_token": token})
    mongo_db.users.delete_one({"user_id": user_id})
    mongo_db.orders.delete_many({"user_id": user_id})


@pytest.fixture(scope="session")
def auth_headers(session_token):
    return {"Authorization": f"Bearer {session_token['token']}",
            "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ==========================================================
# 1. Health
# ==========================================================
class TestHealth:
    def test_root_health(self, api_client):
        r = api_client.get(f"{API}/")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("service") == "curry-co-api"


# ==========================================================
# 2. Seed
# ==========================================================
class TestSeed:
    def test_dev_seed(self, api_client):
        r = api_client.post(f"{API}/dev/seed")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("weeks_seeded") == 3
        assert data.get("packages") == 3
        assert data.get("coupons") == 3


# ==========================================================
# 3-5. Menu + Catering
# ==========================================================
class TestMenuCatering:
    def test_menu_current(self, api_client):
        r = api_client.get(f"{API}/menu/current")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data is not None, "No current-week menu returned"
        assert "week_start" in data and "items" in data
        assert len(data["items"]) >= 1
        item = data["items"][0]
        for key in ("item_id", "name", "price_cents", "image_url", "category"):
            assert key in item, f"missing {key} in menu item"
        # save for reuse
        pytest.first_menu_item_id = item["item_id"]
        pytest.current_week_start = data["week_start"]

    def test_menu_upcoming(self, api_client):
        r = api_client.get(f"{API}/menu/upcoming")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1, "expected at least one upcoming week"
        cur = getattr(pytest, "current_week_start", None)
        for wk in data:
            if cur:
                assert wk["week_start"] > cur, f"upcoming should be > {cur}"

    def test_catering_sorted(self, api_client):
        r = api_client.get(f"{API}/catering")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list) and len(data) == 3
        prices = [p["price_cents"] for p in data]
        assert prices == sorted(prices), f"catering not sorted by price_cents: {prices}"
        for p in data:
            assert "min_guests" in p and "guest_count" not in p
            assert p["price_cents"] in (1999, 2499, 3299)


# ==========================================================
# 6. Coupons
# ==========================================================
class TestCoupons:
    def test_valid_coupon(self, api_client):
        r = api_client.get(f"{API}/coupons/WELCOME10")
        assert r.status_code == 200, r.text
        c = r.json()
        assert c["code"] == "WELCOME10"
        assert c["discount_type"] == "percent"
        assert c["value"] == 10

    def test_invalid_coupon(self, api_client):
        r = api_client.get(f"{API}/coupons/INVALIDCODE")
        assert r.status_code == 404


# ==========================================================
# 7. Auth + Orders + Checkout
# ==========================================================
class TestAuthOrders:
    def test_auth_me(self, api_client, auth_headers, session_token):
        r = api_client.get(f"{API}/auth/me", headers=auth_headers)
        assert r.status_code == 200, r.text
        u = r.json()
        assert u["user_id"] == session_token["user_id"]
        assert u["email"].startswith("TEST_")

    def test_auth_me_unauth(self, api_client):
        r = api_client.get(f"{API}/auth/me")
        assert r.status_code == 401

    def _order_payload(self, item_id, qty=2, coupon=None):
        return {
            "items": [{"kind": "menu", "ref_id": item_id, "quantity": qty}],
            "address": {
                "line1": "123 Test St",
                "line2": "",
                "city": "Toronto",
                "province": "ON",
                "postal_code": "M5V1A1",
                "instructions": "leave at door",
            },
            "slot": {"date": "2026-01-31", "window": "friday_evening"},
            "phone": "6470001234",
            "coupon_code": coupon,
            "redeem_points": 0,
            "special_instructions": "TEST",
        }

    def test_order_quote_with_coupon(self, api_client, auth_headers):
        item_id = getattr(pytest, "first_menu_item_id", None)
        assert item_id, "menu item id not captured"
        # qty=2, item price 1899 => 3798 subtotal >= $20
        payload = self._order_payload(item_id, qty=2, coupon="WELCOME10")
        r = api_client.post(f"{API}/orders/quote", json=payload, headers=auth_headers)
        assert r.status_code == 200, r.text
        q = r.json()
        assert q["subtotal_cents"] > 0
        assert q["delivery_fee_cents"] == 599
        # discount should be applied if subtotal>=$20
        if q["subtotal_cents"] >= 2000:
            assert q["discount_cents"] > 0
            assert q["coupon_code"] == "WELCOME10"
        assert q["total_cents"] == max(
            0, q["subtotal_cents"] + q["delivery_fee_cents"]
            - q["discount_cents"] - q["points_redeemed_cents"]
        ) + q.get("tax_cents", 0)

    def test_create_order_and_verify(self, api_client, auth_headers):
        item_id = getattr(pytest, "first_menu_item_id", None)
        payload = self._order_payload(item_id, qty=2, coupon="WELCOME10")
        r = api_client.post(f"{API}/orders", json=payload, headers=auth_headers)
        assert r.status_code == 200, r.text
        o = r.json()
        assert o.get("order_id", "").startswith("ord_")
        assert o["payment_status"] == "pending"
        assert o["status"] == "pending_payment"
        assert len(o["tracking_events"]) >= 1
        pytest.order_id = o["order_id"]

        # GET list — pending_payment card orders are HIDDEN from list per new spec.
        # Verify a companion COD order shows up instead.
        cod_payload = self._order_payload(item_id, qty=2, coupon="WELCOME10")
        cod_payload["payment_method"] = "cod"
        rcod = api_client.post(f"{API}/orders", json=cod_payload, headers=auth_headers)
        assert rcod.status_code == 200
        cod_id = rcod.json()["order_id"]
        r2 = api_client.get(f"{API}/orders", headers=auth_headers)
        assert r2.status_code == 200
        orders = r2.json()
        ids = [x["order_id"] for x in orders]
        assert cod_id in ids
        assert o["order_id"] not in ids, "pending_payment order should be hidden"

        # GET by id
        r3 = api_client.get(f"{API}/orders/{o['order_id']}", headers=auth_headers)
        assert r3.status_code == 200
        got = r3.json()
        assert got["order_id"] == o["order_id"]
        assert "tracking_events" in got

    def test_checkout_session(self, api_client, auth_headers):
        order_id = getattr(pytest, "order_id", None)
        assert order_id, "order id missing"
        payload = {"order_id": order_id, "origin_url": "https://curry-ecosystem.preview.emergentagent.com"}
        r = api_client.post(f"{API}/checkout/session", json=payload, headers=auth_headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "url" in data and data["url"].startswith("https://")
        assert "session_id" in data and data["session_id"]

    def test_order_status_update(self, api_client):
        order_id = getattr(pytest, "order_id", None)
        r = api_client.post(
            f"{API}/orders/{order_id}/status",
            json={"status": "preparing", "note": "kitchen started"},
        )
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True


# ==========================================================
# 8. Delivery partner
# ==========================================================
class TestDeliveryPartner:
    def test_apply(self, api_client):
        payload = {
            "full_name": "TEST Applicant",
            "email": "TEST_dp@curry.co",
            "phone": "6470001111",
            "city": "Toronto",
            "vehicle": "bike",
            "availability": "part_time",
            "experience": "2 years",
        }
        r = api_client.post(f"{API}/delivery-partner/apply", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("app_id", "").startswith("dp_")


# ==========================================================
# 9. Push register
# ==========================================================
class TestPushRegister:
    def test_register_push(self, api_client, session_token):
        payload = {
            "user_id": session_token["user_id"],
            "platform": "ios",
            "device_token": "TEST_device_token_abc",
        }
        r = api_client.post(f"{API}/register-push", json=payload)
        # endpoint uses status_code=201
        assert r.status_code in (200, 201), r.text



# ==========================================================
# 10. Guest login (NEW) + regression: orders list scoping
# ==========================================================
def _this_week_friday_iso() -> str:
    """Return this calendar week's Friday (Sun-based week, matching backend _sunday_of).
    If today is Sat, still return this week's Friday (already passed)."""
    today = datetime.now(timezone.utc).date()
    # days_since_sun: Sun=0..Sat=6 (matches server._sunday_of logic)
    days_since_sun = (today.weekday() + 1) % 7
    sunday = today - timedelta(days=days_since_sun)
    friday = sunday + timedelta(days=5)
    return friday.isoformat()


def _make_order_payload(item_id: str, qty: int = 2, coupon: str | None = None,
                         slot_date: str | None = None):
    return {
        "items": [{"kind": "menu", "ref_id": item_id, "quantity": qty}],
        "address": {
            "line1": "123 Guest St",
            "line2": "",
            "city": "Toronto",
            "province": "ON",
            "postal_code": "M5V1A1",
            "instructions": "leave at door",
        },
        "slot": {"date": slot_date or _this_week_friday_iso(),
                  "window": "friday_evening"},
        "phone": "6470005678",
        "coupon_code": coupon,
        "redeem_points": 0,
        "special_instructions": "TEST guest order",
    }


@pytest.fixture(scope="function")
def guest_session(mongo_db, api_client):
    """Create a fresh guest via POST /api/auth/guest and clean up after."""
    r = api_client.post(f"{API}/auth/guest")
    assert r.status_code == 200, r.text
    data = r.json()
    yield data
    # teardown
    try:
        uid = data["user"]["user_id"]
        mongo_db.user_sessions.delete_many({"user_id": uid})
        mongo_db.users.delete_one({"user_id": uid})
        mongo_db.orders.delete_many({"user_id": uid})
    except Exception:
        pass


class TestGuestAuth:
    """POST /api/auth/guest — creates guest user + 7d session."""

    def test_guest_login_shape(self, guest_session):
        assert "session_token" in guest_session and guest_session["session_token"]
        u = guest_session["user"]
        assert u["role"] == "guest"
        assert u["name"] == "Guest"
        assert u["user_id"].startswith("guest_")
        # token prefix is a convention in backend
        assert guest_session["session_token"].startswith("guest-")

    def test_guest_token_authenticates_me(self, api_client, guest_session):
        headers = {"Authorization": f"Bearer {guest_session['session_token']}"}
        r = api_client.get(f"{API}/auth/me", headers=headers)
        assert r.status_code == 200, r.text
        me = r.json()
        assert me["user_id"] == guest_session["user"]["user_id"]
        assert me["role"] == "guest"


class TestGuestOrdersE2E:
    """Regression: guest can quote + create order, and GET /api/orders returns it."""

    def test_full_flow_and_orders_list_contains_new_order(self, api_client, guest_session):
        headers = {"Authorization": f"Bearer {guest_session['session_token']}",
                   "Content-Type": "application/json"}
        # Fetch current menu
        r = api_client.get(f"{API}/menu/current")
        assert r.status_code == 200, r.text
        menu = r.json()
        assert menu and menu.get("items"), "no current menu items"
        item_id = menu["items"][0]["item_id"]

        # 1. Quote with WELCOME10 (subtotal must be >= $20)
        payload = _make_order_payload(item_id, qty=2, coupon="WELCOME10")
        rq = api_client.post(f"{API}/orders/quote", json=payload, headers=headers)
        assert rq.status_code == 200, rq.text
        q = rq.json()
        assert q["subtotal_cents"] >= 2000, f"subtotal too low: {q['subtotal_cents']}"
        assert q["coupon_code"] == "WELCOME10"
        assert q["discount_cents"] > 0

        # 2. Create order (COD so it appears in orders list under new spec)
        payload["payment_method"] = "cod"
        rc = api_client.post(f"{API}/orders", json=payload, headers=headers)
        assert rc.status_code == 200, rc.text
        order = rc.json()
        order_id = order["order_id"]
        assert order_id.startswith("ord_")
        assert order["user_id"] == guest_session["user"]["user_id"]

        # 3. KEY REGRESSION: GET /api/orders with same token must include this order
        rl = api_client.get(f"{API}/orders", headers=headers)
        assert rl.status_code == 200, rl.text
        orders_list = rl.json()
        assert isinstance(orders_list, list)
        ids = [o["order_id"] for o in orders_list]
        assert order_id in ids, (
            f"Orders-tab regression: newly-created order {order_id} NOT returned by "
            f"GET /api/orders. Got: {ids}"
        )

        # 4. GET /api/orders/{id}
        rg = api_client.get(f"{API}/orders/{order_id}", headers=headers)
        assert rg.status_code == 200, rg.text
        full = rg.json()
        assert full["order_id"] == order_id
        assert full["user_id"] == guest_session["user"]["user_id"]

        # 5. Checkout session — must use a card order (COD returns 400)
        card_payload = _make_order_payload(item_id, qty=2, coupon="WELCOME10")
        card_payload["payment_method"] = "card"
        rcc = api_client.post(f"{API}/orders", json=card_payload, headers=headers)
        assert rcc.status_code == 200, rcc.text
        card_oid = rcc.json()["order_id"]
        rs = api_client.post(
            f"{API}/checkout/session",
            json={"order_id": card_oid,
                  "origin_url": "https://curry-ecosystem.preview.emergentagent.com"},
            headers=headers,
        )
        assert rs.status_code == 200, rs.text
        cs = rs.json()
        assert cs.get("url", "").startswith("https://checkout.stripe.com"), (
            f"expected Stripe checkout URL, got: {cs.get('url')}"
        )
        assert cs.get("session_id")


class TestOrdersScoping:
    """Per-user scoping: order created by guest A must NOT appear for guest B."""

    def test_orders_are_user_scoped(self, api_client, mongo_db):
        # create two guests
        ra = api_client.post(f"{API}/auth/guest")
        rb = api_client.post(f"{API}/auth/guest")
        assert ra.status_code == 200 and rb.status_code == 200
        ga, gb = ra.json(), rb.json()
        ha = {"Authorization": f"Bearer {ga['session_token']}",
              "Content-Type": "application/json"}
        hb = {"Authorization": f"Bearer {gb['session_token']}",
              "Content-Type": "application/json"}
        try:
            # get an item id
            m = api_client.get(f"{API}/menu/current").json()
            item_id = m["items"][0]["item_id"]

            # A places one order (COD so it stays visible in list under new spec)
            payload = _make_order_payload(item_id, qty=2, coupon="WELCOME10")
            payload["payment_method"] = "cod"
            rc = api_client.post(f"{API}/orders", json=payload, headers=ha)
            assert rc.status_code == 200, rc.text
            oid = rc.json()["order_id"]

            # A sees it
            la = api_client.get(f"{API}/orders", headers=ha)
            assert la.status_code == 200
            assert any(o["order_id"] == oid for o in la.json()), \
                "guest A's own order missing from their orders list"

            # B sees empty
            lb = api_client.get(f"{API}/orders", headers=hb)
            assert lb.status_code == 200
            assert lb.json() == [], (
                f"guest B leaked A's orders: got {lb.json()}"
            )
        finally:
            for g in (ga, gb):
                uid = g["user"]["user_id"]
                mongo_db.user_sessions.delete_many({"user_id": uid})
                mongo_db.users.delete_one({"user_id": uid})
                mongo_db.orders.delete_many({"user_id": uid})


class TestGoogleAuthInvalid:
    """Regression: /api/auth/session with an invalid session_token returns 401."""

    def test_invalid_session_token_401(self, api_client):
        r = api_client.post(
            f"{API}/auth/session",
            json={"session_token": f"invalid_{uuid.uuid4().hex}"},
        )
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"
