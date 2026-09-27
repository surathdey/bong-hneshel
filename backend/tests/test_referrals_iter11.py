"""
Referral iteration 11 backend tests — additive features on top of iter10:

Covers:
  * GET  /api/referrals/me    — new fields `you_were_referred` and
                                `your_bonus_status` ('available'|'used'|'none').
  * GET  /api/admin/referrals/leaderboard (admin JWT) — ranked list of referrers
                                with points_earned and reward_points.
  * COD friend discount:
      - referred friend's 1st COD order has referral_discount_cents > 0 (10%),
      - referrer gets +100 loyalty points once,
      - friend's 2nd order has referral_discount_cents == 0 (rule: one-time),
      - referrer is NOT rewarded a second time (idempotent).
  * POST /api/referrals/redeem — user who is already referred can't redeem
                                 another code (returns 400).

Only COD is exercised — LIVE Stripe key is loaded server-side.
"""

import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL",
                          "https://clone-verify-2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@bong-hneshel.ca"
ADMIN_PASSWORD = "DDuCi!dZ0UmN3vXu"


# ---------------------------- helpers ----------------------------
def _rand_email(tag: str = "ref11") -> str:
    return f"TEST_{tag}_{uuid.uuid4().hex[:10]}@bhtest-example.com"


def _register(email: str, password: str = "TestPass1234!", name: str = "Iter11 User",
              referral_code: str | None = None) -> dict:
    body = {"email": email, "password": password, "name": name}
    if referral_code is not None:
        body["referral_code"] = referral_code
    r = requests.post(f"{API}/auth/register", json=body, timeout=30)
    return {"status": r.status_code,
            "json": r.json() if r.headers.get("content-type", "").startswith("application/json") else {}}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _admin_token() -> str:
    r = requests.post(f"{API}/admin/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _me(token: str) -> dict:
    r = requests.get(f"{API}/auth/me", headers=_auth(token), timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _referral_me(token: str) -> dict:
    r = requests.get(f"{API}/referrals/me", headers=_auth(token), timeout=15)
    return r


def _get_orderable_item() -> dict:
    r = requests.get(f"{API}/menu/anytime", timeout=15)
    if r.status_code == 200 and isinstance(r.json(), list) and r.json():
        return r.json()[0]
    r2 = requests.get(f"{API}/menu/current", timeout=15)
    assert r2.status_code == 200
    items = (r2.json() or {}).get("items") or []
    assert items, "no menu items"
    return items[0]


def _address() -> dict:
    return {
        "name": "Iter11 Buyer",
        "email": "iter11@bhtest-example.com",
        "line1": "123 Bloor St W",
        "line2": "",
        "city": "Toronto",
        "province": "ON",
        "postal_code": "M5S 1M1",
        "lat": 43.6667,
        "lng": -79.4000,
        "instructions": "",
    }


def _slot() -> dict:
    return {"date": "2026-01-24", "window": "saturday_morning"}


def _order_body(item_id: str) -> dict:
    return {
        "items": [{"kind": "menu", "ref_id": item_id, "quantity": 2}],
        "address": _address(),
        "slot": _slot(),
        "phone": "+14165550100",
        "coupon_code": None,
        "redeem_points": 0,
        "special_instructions": "",
        "payment_method": "cod",
    }


# --------------------- fixtures ---------------------
@pytest.fixture(scope="module")
def admin_token():
    return _admin_token()


@pytest.fixture(scope="module")
def orderable_item():
    return _get_orderable_item()


@pytest.fixture(scope="module", autouse=True)
def ensure_default_referral(admin_token):
    """Snapshot admin settings and force canonical referral config."""
    r = requests.get(f"{API}/admin/settings",
                     headers=_auth(admin_token), timeout=15)
    assert r.status_code == 200, r.text
    snap = r.json()
    payload = dict(snap)
    payload["referral_enabled"] = True
    payload["referral_reward_points"] = 100
    payload["referral_friend_discount_type"] = "percent"
    payload["referral_friend_discount_value"] = 10
    payload.pop("_id", None)
    payload.pop("key", None)
    r = requests.put(f"{API}/admin/settings", json=payload,
                     headers=_auth(admin_token), timeout=15)
    assert r.status_code == 200, f"prime settings failed: {r.status_code} {r.text}"
    yield


# --------------------- tests ---------------------
# GET /referrals/me — new fields
class TestReferralsMeStatusFields:
    def test_non_referred_user_has_none_status(self):
        r = _register(_rand_email("solo"))
        assert r["status"] == 200
        token = r["json"]["session_token"]
        body = _referral_me(token).json()
        assert body.get("you_were_referred") is False
        assert body.get("your_bonus_status") == "none"

    def test_referred_user_available_before_order(self):
        # Referrer
        r_ref = _register(_rand_email("Rme"))
        code = _referral_me(r_ref["json"]["session_token"]).json()["code"]
        # Friend registers with the code -> should be linked immediately
        r_fr = _register(_rand_email("Fme"), referral_code=code)
        assert r_fr["status"] == 200
        ft = r_fr["json"]["session_token"]
        body = _referral_me(ft).json()
        assert body["you_were_referred"] is True, body
        assert body["your_bonus_status"] == "available", body

    def test_referred_user_used_after_first_order(self, orderable_item):
        r_ref = _register(_rand_email("Rused"))
        code = _referral_me(r_ref["json"]["session_token"]).json()["code"]
        r_fr = _register(_rand_email("Fused"), referral_code=code)
        ft = r_fr["json"]["session_token"]
        # Place a COD order
        o = requests.post(f"{API}/orders", json=_order_body(orderable_item["item_id"]),
                          headers=_auth(ft), timeout=30)
        assert o.status_code == 200, o.text
        body = _referral_me(ft).json()
        assert body["you_were_referred"] is True
        assert body["your_bonus_status"] == "used", body


# GET /admin/referrals/leaderboard
class TestAdminLeaderboard:
    def test_leaderboard_shape_and_reward_points(self, admin_token):
        r = requests.get(f"{API}/admin/referrals/leaderboard",
                         headers=_auth(admin_token), timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "leaderboard" in body and isinstance(body["leaderboard"], list)
        assert body.get("reward_points") == 100
        if body["leaderboard"]:
            row = body["leaderboard"][0]
            for k in ("referrer_id", "name", "email", "code",
                      "invited", "rewarded", "points_earned", "loyalty_points"):
                assert k in row, f"missing {k}: {row}"

    def test_leaderboard_requires_admin(self):
        r = requests.get(f"{API}/admin/referrals/leaderboard", timeout=15)
        assert r.status_code in (401, 403), r.text

    def test_leaderboard_sort_order(self, admin_token, orderable_item):
        """Create two referrers where one has a rewarded referral and verify
        sort places rewarded > invited-only."""
        # Referrer A gets 1 friend that ORDERS
        rA = _register(_rand_email("LA"))
        codeA = _referral_me(rA["json"]["session_token"]).json()["code"]
        fA = _register(_rand_email("LFa"), referral_code=codeA)
        oa = requests.post(f"{API}/orders", json=_order_body(orderable_item["item_id"]),
                           headers=_auth(fA["json"]["session_token"]), timeout=30)
        assert oa.status_code == 200, oa.text

        # Referrer B just gets 1 invite (no order)
        rB = _register(_rand_email("LB"))
        codeB = _referral_me(rB["json"]["session_token"]).json()["code"]
        _register(_rand_email("LFb"), referral_code=codeB)

        r = requests.get(f"{API}/admin/referrals/leaderboard",
                         headers=_auth(admin_token), timeout=20)
        body = r.json()
        # Extract A / B positions
        idx = {row["referrer_id"]: i for i, row in enumerate(body["leaderboard"])}
        ida = _me(rA["json"]["session_token"])["user_id"]
        idb = _me(rB["json"]["session_token"])["user_id"]
        assert ida in idx and idb in idx, idx
        assert idx[ida] < idx[idb], f"A (rewarded) should rank above B (invited only): {body['leaderboard']}"
        rowA = body["leaderboard"][idx[ida]]
        assert rowA["rewarded"] >= 1
        assert rowA["points_earned"] >= 100


# One-time referral rule
class TestOneTimeReferralRule:
    def test_friend_discount_only_on_first_order(self, orderable_item):
        r_ref = _register(_rand_email("ROT"))
        rt = r_ref["json"]["session_token"]
        code = _referral_me(rt).json()["code"]
        r_fr = _register(_rand_email("FOT"), referral_code=code)
        ft = r_fr["json"]["session_token"]

        # 1st COD order — should have referral_discount_cents > 0
        q1 = requests.post(f"{API}/orders/quote",
                           json=_order_body(orderable_item["item_id"]),
                           headers=_auth(ft), timeout=20)
        assert q1.status_code == 200, q1.text
        body1 = q1.json()
        subtotal = body1["subtotal_cents"]
        expected = subtotal * 10 // 100
        assert body1.get("referral_discount_cents") == expected, body1
        assert body1.get("discount_cents", 0) == 0  # no coupon

        o1 = requests.post(f"{API}/orders",
                           json=_order_body(orderable_item["item_id"]),
                           headers=_auth(ft), timeout=30)
        assert o1.status_code == 200, o1.text
        first_order = o1.json()
        assert first_order.get("referral_discount_cents") == expected

        # Referrer should be rewarded exactly once
        ref_me = _referral_me(rt).json()
        assert ref_me["rewarded_count"] >= 1
        assert ref_me["points_earned"] >= 100
        referrer_points_after_1 = _me(rt).get("loyalty_points", 0)
        rewarded_after_1 = ref_me["rewarded_count"]

        # 2nd quote — no more friend discount
        q2 = requests.post(f"{API}/orders/quote",
                           json=_order_body(orderable_item["item_id"]),
                           headers=_auth(ft), timeout=20)
        assert q2.status_code == 200, q2.text
        assert q2.json().get("referral_discount_cents", 0) == 0, q2.json()

        # 2nd order — still no referral discount + no double reward
        o2 = requests.post(f"{API}/orders",
                           json=_order_body(orderable_item["item_id"]),
                           headers=_auth(ft), timeout=30)
        assert o2.status_code == 200, o2.text
        assert o2.json().get("referral_discount_cents", 0) == 0

        ref_me2 = _referral_me(rt).json()
        assert ref_me2["rewarded_count"] == rewarded_after_1, ref_me2
        referrer_points_after_2 = _me(rt).get("loyalty_points", 0)
        assert referrer_points_after_2 == referrer_points_after_1, (
            f"Referrer got double-rewarded! {referrer_points_after_1} -> {referrer_points_after_2}")

    def test_already_referred_user_cant_redeem_new_code(self, orderable_item):
        # Referrer 1 -> friend F is already linked at signup
        r1 = _register(_rand_email("Rdouble"))
        c1 = _referral_me(r1["json"]["session_token"]).json()["code"]
        r_fr = _register(_rand_email("Fdouble"), referral_code=c1)
        ft = r_fr["json"]["session_token"]
        # Confirm bonus available
        assert _referral_me(ft).json()["your_bonus_status"] == "available"

        # A DIFFERENT referrer 2's code
        r2 = _register(_rand_email("Rother"))
        c2 = _referral_me(r2["json"]["session_token"]).json()["code"]

        # Try to redeem — must be 400
        rr = requests.post(f"{API}/referrals/redeem", json={"code": c2},
                           headers=_auth(ft), timeout=15)
        assert rr.status_code == 400, rr.text
