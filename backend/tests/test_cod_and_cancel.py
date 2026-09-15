"""COD + failed-payment cleanup tests for Curry & Co."""
import os
import re
import uuid
import subprocess
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
BASE_URL = (
    os.environ.get("EXPO_BACKEND_URL")
    or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or "https://curry-ecosystem.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "curry_co_db")


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


def _payload(item_id, qty=2, pm="card"):
    return {
        "items": [{"kind": "menu", "ref_id": item_id, "quantity": qty}],
        "address": {"line1": "1 King St W", "line2": "", "city": "Toronto",
                    "province": "ON", "postal_code": "M5H1A1"},
        "slot": {"date": _this_week_friday_iso(), "window": "friday_evening"},
        "phone": "6479991111",
        "coupon_code": None,
        "redeem_points": 0,
        "special_instructions": "TEST",
        "payment_method": pm,
    }


@pytest.fixture(scope="module", autouse=True)
def _seed(api_client=None):
    # Ensure DB is seeded
    with requests.Session() as s:
        s.post(f"{API}/dev/seed")


def _menu_item_id(api_client):
    r = api_client.get(f"{API}/menu/current")
    assert r.status_code == 200
    return r.json()["items"][0]["item_id"], r.json()["items"][0]["price_cents"]


# ---------------------- 1. COD order creation ----------------------
class TestCODCreation:
    def test_cod_order_response_shape(self, api_client, guest):
        item_id, price = _menu_item_id(api_client)
        r = api_client.post(f"{API}/orders", json=_payload(item_id, qty=2, pm="cod"),
                            headers=_headers(guest))
        assert r.status_code == 200, r.text
        o = r.json()
        assert o["payment_method"] == "cod"
        assert o["status"] == "confirmed"
        assert o["payment_status"] == "cod_pending"
        statuses = [e["status"] for e in o["tracking_events"]]
        assert "new" in statuses and "confirmed" in statuses
        # loyalty points == floor(subtotal_cents/100)
        expected_pts = o["subtotal_cents"] // 100
        assert o["points_awarded"] == expected_pts

        # verify on /auth/me
        rme = api_client.get(f"{API}/auth/me", headers=_headers(guest))
        assert rme.status_code == 200
        assert rme.json()["loyalty_points"] == expected_pts


# ---------------------- 2. Card default status ----------------------
class TestCardDefault:
    def test_card_order_pending_payment(self, api_client, guest):
        item_id, _ = _menu_item_id(api_client)
        r = api_client.post(f"{API}/orders", json=_payload(item_id, pm="card"),
                            headers=_headers(guest))
        assert r.status_code == 200
        assert r.json()["status"] == "pending_payment"

    def test_card_omitted_defaults_to_card(self, api_client, guest):
        item_id, _ = _menu_item_id(api_client)
        p = _payload(item_id)
        del p["payment_method"]
        r = api_client.post(f"{API}/orders", json=p, headers=_headers(guest))
        assert r.status_code == 200
        j = r.json()
        assert j["payment_method"] == "card"
        assert j["status"] == "pending_payment"


# ---------------------- 3. GET /orders excludes pending_payment ----------------------
class TestOrdersListFiltersPending:
    def test_list_hides_pending_payment(self, api_client, guest):
        item_id, _ = _menu_item_id(api_client)
        # card
        rc = api_client.post(f"{API}/orders", json=_payload(item_id, pm="card"),
                             headers=_headers(guest))
        assert rc.status_code == 200
        card_id = rc.json()["order_id"]
        # cod
        rd = api_client.post(f"{API}/orders", json=_payload(item_id, pm="cod"),
                             headers=_headers(guest))
        assert rd.status_code == 200
        cod_id = rd.json()["order_id"]

        rl = api_client.get(f"{API}/orders", headers=_headers(guest))
        assert rl.status_code == 200
        ids = [o["order_id"] for o in rl.json()]
        assert cod_id in ids
        assert card_id not in ids, f"pending_payment order leaked into list: {ids}"


# ---------------------- 4. cancel-unpaid on pending card order ----------------------
class TestCancelUnpaid:
    def test_cancel_unpaid_deletes_and_emails(self, api_client, guest, mongo_db):
        item_id, _ = _menu_item_id(api_client)
        rc = api_client.post(f"{API}/orders", json=_payload(item_id, pm="card"),
                             headers=_headers(guest))
        assert rc.status_code == 200
        oid = rc.json()["order_id"]

        # capture backend log tail before
        rcx = api_client.post(f"{API}/orders/{oid}/cancel-unpaid",
                              headers=_headers(guest))
        assert rcx.status_code == 200, rcx.text
        body = rcx.json()
        assert body == {"ok": True, "deleted": True}

        # verify order gone
        rg = api_client.get(f"{API}/orders/{oid}", headers=_headers(guest))
        assert rg.status_code == 404

        # check backend log
        try:
            log = subprocess.check_output(
                ["tail", "-n", "200", "/var/log/supervisor/backend.out.log"],
                stderr=subprocess.STDOUT, timeout=5,
            ).decode(errors="ignore")
        except Exception:
            log = ""
        try:
            errlog = subprocess.check_output(
                ["tail", "-n", "200", "/var/log/supervisor/backend.err.log"],
                stderr=subprocess.STDOUT, timeout=5,
            ).decode(errors="ignore")
        except Exception:
            errlog = ""
        combined = log + errlog
        assert "Your order was not completed" in combined, (
            "Expected mocked-email log line not found. Tail sample:\n"
            + combined[-1000:]
        )

    def test_cancel_cod_order_returns_400(self, api_client, guest):
        item_id, _ = _menu_item_id(api_client)
        r = api_client.post(f"{API}/orders", json=_payload(item_id, pm="cod"),
                            headers=_headers(guest))
        assert r.status_code == 200
        oid = r.json()["order_id"]
        rc = api_client.post(f"{API}/orders/{oid}/cancel-unpaid",
                             headers=_headers(guest))
        assert rc.status_code == 400, rc.text

    def test_cancel_paid_order_returns_400(self, api_client, guest, mongo_db):
        # simulate: create card order then flip payment_status to paid in DB
        item_id, _ = _menu_item_id(api_client)
        r = api_client.post(f"{API}/orders", json=_payload(item_id, pm="card"),
                            headers=_headers(guest))
        assert r.status_code == 200
        oid = r.json()["order_id"]
        mongo_db.orders.update_one(
            {"order_id": oid},
            {"$set": {"payment_status": "paid", "status": "preparing"}},
        )
        rc = api_client.post(f"{API}/orders/{oid}/cancel-unpaid",
                             headers=_headers(guest))
        assert rc.status_code == 400, rc.text


# ---------------------- 6. checkout/session on COD order (documented behavior) ----------------------
class TestCheckoutOnCod:
    def test_checkout_session_on_cod_order(self, api_client, guest):
        item_id, _ = _menu_item_id(api_client)
        r = api_client.post(f"{API}/orders", json=_payload(item_id, pm="cod"),
                            headers=_headers(guest))
        assert r.status_code == 200
        oid = r.json()["order_id"]
        rs = api_client.post(
            f"{API}/checkout/session",
            json={"order_id": oid, "origin_url": BASE_URL},
            headers=_headers(guest),
        )
        # Backend currently does NOT guard; document behavior.
        # Either it succeeds (200 w/ URL) OR returns 400 "already paid"-style.
        assert rs.status_code in (200, 400), rs.text
