"""Backend tests for FIRST-TIME COUPON feature (iteration 6).

Covers:
- GET /api/coupons/first-time (member vs guest)
- POST /api/orders/quote with FIRST10 (member) yields 10% off
- Guest gating: quote with FIRST10 gives 0 discount and no coupon_code
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://clone-verify-2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

MEMBER_TOKEN = "testmember-loyalty-2026"
MASTER_ITEM_ID = "mi_a7b61af064"


@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def guest_token(s):
    r = s.post(f"{API}/auth/guest", timeout=15)
    assert r.status_code == 200, f"guest auth failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("session_token") or data.get("token") or data.get("access_token")
    assert tok, f"no token in guest response: {data}"
    return tok


# ---------- /coupons/first-time ----------

def test_first_time_coupon_member_returns_first10(s):
    r = s.get(f"{API}/coupons/first-time", headers={"Authorization": f"Bearer {MEMBER_TOKEN}"}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("coupon") is not None, f"expected coupon for member, got {body}"
    c = body["coupon"]
    assert c.get("code") == "FIRST10", c
    assert int(c.get("value")) == 10, c
    # sanity: it must be flagged first-time-only + percent
    assert c.get("first_time_only") is True
    assert c.get("discount_type") == "percent"


def test_first_time_coupon_guest_returns_null(s, guest_token):
    r = s.get(f"{API}/coupons/first-time", headers={"Authorization": f"Bearer {guest_token}"}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("coupon") is None, f"guest should not receive coupon, got {body}"


# ---------- /orders/quote with FIRST10 ----------

QUOTE_BODY = {
    "items": [{"kind": "menu", "ref_id": MASTER_ITEM_ID, "quantity": 5}],
    "address": {"line1": "1 King St", "city": "Toronto", "postal_code": "M5H1A1"},
    "slot": {"date": "2026-09-20", "window": "saturday_morning"},
    "payment_method": "cod",
    "coupon_code": "FIRST10",
}


def test_quote_member_applies_first10(s):
    r = s.post(
        f"{API}/orders/quote",
        json=QUOTE_BODY,
        headers={"Authorization": f"Bearer {MEMBER_TOKEN}"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    q = r.json()
    assert q.get("subtotal_cents") == 10000, q
    assert q.get("discount_cents") == 1000, q
    assert q.get("coupon_code") == "FIRST10", q
    assert q.get("total_cents") == 9000, q


def test_quote_guest_cannot_use_first10(s, guest_token):
    r = s.post(
        f"{API}/orders/quote",
        json=QUOTE_BODY,
        headers={"Authorization": f"Bearer {guest_token}"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    q = r.json()
    assert q.get("subtotal_cents") == 10000, q
    assert q.get("discount_cents") == 0, f"guest must not receive discount, got {q}"
    assert q.get("coupon_code") in (None, ""), f"guest coupon_code must be null, got {q}"
