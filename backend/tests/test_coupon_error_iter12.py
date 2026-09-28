"""
Iteration 12 - Coupon error surfacing bug fix.

Scenarios per review request:
  (a) NEW customer + WELCOME20 => coupon_code=WELCOME20, discount>0, coupon_error=null
  (b) Customer with prior COD order + WELCOME20 => coupon_error="You've already used this first-order coupon."
  (c) Invalid code NOPE99 => coupon_error="This coupon code isn't valid."
  (d) No coupon => coupon_error=null

Regressions:
  - COD order still placeable
  - First-order coupon still discounts first order
  - referral_discount_cents field still present
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"
BASE_URL = BASE_URL.rstrip("/")

MENU_ITEM_ID = "mi_f009e056c7"


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _register(http, email=None, password="Testpass123!"):
    email = email or f"test_coupon_{uuid.uuid4().hex[:10]}@example.com"
    r = http.post(f"{BASE_URL}/api/auth/register", json={
        "email": email, "password": password, "name": "Coupon Tester"
    })
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    data = r.json()
    token = data.get("session_token") or data.get("token") or data.get("access_token")
    assert token, f"no token in register response: {data}"
    return email, password, token


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _sample_address():
    return {
        "name": "Coupon Tester",
        "email": "coupon@bhtest-example.com",
        "line1": "100 Queen St W",
        "line2": "",
        "city": "Toronto",
        "province": "ON",
        "postal_code": "M5H 2N2",
        "lat": 43.6534817,
        "lng": -79.3839347,
        "instructions": "",
    }


def _sample_slot():
    return {"date": "2026-01-24", "window": "saturday_morning"}


def _quote_payload(coupon_code=None):
    p = {
        "items": [{"kind": "menu", "ref_id": MENU_ITEM_ID, "quantity": 2}],
        "address": _sample_address(),
        "slot": _sample_slot(),
        "phone": "+14165550100",
        "redeem_points": 0,
        "special_instructions": "",
        "payment_method": "cod",
    }
    if coupon_code is not None:
        p["coupon_code"] = coupon_code
    return p


# ---------- 0. sanity: welcome20 coupon exists & active ----------
def test_welcome20_active(http):
    r = http.get(f"{BASE_URL}/api/coupons/WELCOME20")
    assert r.status_code == 200, f"WELCOME20 must exist: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("active") is True
    assert body.get("first_time_only") is True


# ---------- (a) NEW customer + WELCOME20 => applies ----------
def test_new_customer_welcome20_applies(http):
    email, pw, token = _register(http)
    r = http.post(f"{BASE_URL}/api/orders/quote", json=_quote_payload("WELCOME20"), headers=_auth_headers(token))
    assert r.status_code == 200, f"quote failed: {r.status_code} {r.text}"
    q = r.json()
    assert q.get("coupon_code") == "WELCOME20", q
    assert q.get("discount_cents", 0) > 0, q
    assert q.get("coupon_error") is None, q
    # Regression field
    assert "referral_discount_cents" in q


# ---------- (c) invalid code ----------
def test_invalid_code_error(http):
    _, _, token = _register(http)
    r = http.post(f"{BASE_URL}/api/orders/quote", json=_quote_payload("NOPE99"), headers=_auth_headers(token))
    assert r.status_code == 200, r.text
    q = r.json()
    assert q.get("coupon_code") is None
    assert q.get("discount_cents", 0) == 0
    assert q.get("coupon_error") == "This coupon code isn't valid.", q


# ---------- (d) no coupon => coupon_error null ----------
def test_no_coupon_no_error(http):
    _, _, token = _register(http)
    r = http.post(f"{BASE_URL}/api/orders/quote", json=_quote_payload(None), headers=_auth_headers(token))
    assert r.status_code == 200, r.text
    q = r.json()
    assert q.get("coupon_code") is None
    assert q.get("coupon_error") is None


# ---------- (b) already-used first-order coupon ----------
# This is the core bug fix. Register a fresh user, place a COD order, then quote
# again with WELCOME20 => must surface the "already used" error.
def test_already_used_first_order_coupon(http):
    email, pw, token = _register(http)
    headers = _auth_headers(token)

    # Place one COD order first (no coupon so first-order coupon remains unused
    # but user has 1 prior non-cancelled order -> ineligible for first-time).
    order_payload = _quote_payload(None)
    r_ord = http.post(f"{BASE_URL}/api/orders", json=order_payload, headers=headers)
    assert r_ord.status_code in (200, 201), f"cod order failed: {r_ord.status_code} {r_ord.text}"
    order = r_ord.json()
    # Confirm status
    assert order.get("status") in ("confirmed", "new", "pending_payment"), order

    # Now quote WELCOME20 again -> must show already-used error
    r = http.post(f"{BASE_URL}/api/orders/quote", json=_quote_payload("WELCOME20"), headers=headers)
    assert r.status_code == 200, r.text
    q = r.json()
    assert q.get("coupon_code") is None, q
    assert q.get("discount_cents", 0) == 0, q
    assert q.get("coupon_error") == "You've already used this first-order coupon.", q


# ---------- Regression: first-order coupon still discounts real order ----------
def test_first_order_coupon_discounts_real_order(http):
    _, _, token = _register(http)
    headers = _auth_headers(token)

    order_payload = _quote_payload("WELCOME20")
    r = http.post(f"{BASE_URL}/api/orders", json=order_payload, headers=headers)
    assert r.status_code in (200, 201), f"order create failed: {r.status_code} {r.text}"
    o = r.json()
    assert o.get("coupon_code") == "WELCOME20", o
    assert o.get("discount_cents", 0) > 0, o
    # referral_discount_cents field must still be present (separate from coupon discount)
    assert "referral_discount_cents" in o
