"""
Referral / Invite program end-to-end tests (iteration 10).

Covers:
  * GET  /api/referrals/me            — guest 403, authenticated returns code + stats
  * POST /api/auth/register           — referral_code linking (valid/invalid/self/none)
  * POST /api/referrals/redeem        — success + reject invalid/self/already-referred/already-ordered
  * POST /api/orders/quote            — friend first-order discount (referred vs non-referred)
  * POST /api/orders (COD)            — friend gets discount, referrer earns points on 1st paid order
  * Reward idempotency                — 2nd order by same friend does NOT re-reward
  * Admin PUT/GET /api/admin/settings — referral_* fields persist
  * referral_enabled = false          — no discount + no reward

CRITICAL: only cod payments — a LIVE Stripe key is loaded server-side.
"""

import os
import uuid
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://clone-verify-2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@bong-hneshel.ca"
ADMIN_PASSWORD = "DDuCi!dZ0UmN3vXu"


# ---------------------------- helpers ----------------------------
def _rand_email(tag: str = "ref") -> str:
    # NOTE: pydantic EmailStr rejects reserved TLDs like `.local` / `.test`.
    return f"TEST_{tag}_{uuid.uuid4().hex[:10]}@bhtest-example.com"


def _register(email: str, password: str = "TestPass1234!", name: str = "Test User",
              referral_code: str | None = None) -> dict:
    body = {"email": email, "password": password, "name": name}
    if referral_code is not None:
        body["referral_code"] = referral_code
    r = requests.post(f"{API}/auth/register", json=body, timeout=20)
    return {"status": r.status_code, "json": r.json() if r.headers.get("content-type", "").startswith("application/json") else {}}


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _admin_token() -> str:
    r = requests.post(f"{API}/admin/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _get_orderable_item() -> dict:
    r = requests.get(f"{API}/menu/anytime", timeout=15)
    if r.status_code == 200 and isinstance(r.json(), list) and r.json():
        return r.json()[0]
    r2 = requests.get(f"{API}/menu/current", timeout=15)
    assert r2.status_code == 200, f"no orderable item source: {r2.status_code}"
    body = r2.json()
    items = body.get("items") or []
    assert items, "menu/current returned no items"
    return items[0]


def _address() -> dict:
    return {
        "name": "Test User",
        "email": "test@bhtest-example.com",
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


def _order_body(item_id: str, payment_method: str = "cod", coupon: str | None = None) -> dict:
    body = {
        "items": [{"kind": "menu", "ref_id": item_id, "quantity": 2}],
        "address": _address(),
        "slot": _slot(),
        "phone": "+14165550100",
        "coupon_code": coupon,
        "redeem_points": 0,
        "special_instructions": "",
        "payment_method": payment_method,
    }
    return body


def _me(token: str) -> dict:
    r = requests.get(f"{API}/auth/me", headers=_auth_headers(token), timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _referral_me(token: str) -> dict:
    r = requests.get(f"{API}/referrals/me", headers=_auth_headers(token), timeout=15)
    return r


# --------------------- session-scoped fixtures ---------------------
@pytest.fixture(scope="module")
def admin_token():
    return _admin_token()


@pytest.fixture(scope="module")
def orderable_item():
    return _get_orderable_item()


@pytest.fixture(scope="module")
def original_settings(admin_token):
    """Snapshot admin settings and restore after this module runs."""
    r = requests.get(f"{API}/admin/settings",
                     headers=_auth_headers(admin_token), timeout=15)
    assert r.status_code == 200, r.text
    snap = r.json()
    yield snap
    # Restore known referral defaults (safe subset)
    restore = dict(snap)
    restore["referral_enabled"] = True
    restore["referral_reward_points"] = 100
    restore["referral_friend_discount_type"] = "percent"
    restore["referral_friend_discount_value"] = 10
    # Remove server-only keys before PUT (BusinessSettings tolerates extras via model)
    restore.pop("_id", None)
    restore.pop("key", None)
    requests.put(f"{API}/admin/settings", json=restore,
                 headers=_auth_headers(admin_token), timeout=15)


@pytest.fixture(scope="module", autouse=True)
def ensure_default_referral(admin_token, original_settings):
    """Force the canonical referral config (percent 10 / 100 pts / enabled) at module start."""
    payload = dict(original_settings)
    payload["referral_enabled"] = True
    payload["referral_reward_points"] = 100
    payload["referral_friend_discount_type"] = "percent"
    payload["referral_friend_discount_value"] = 10
    payload.pop("_id", None)
    payload.pop("key", None)
    r = requests.put(f"{API}/admin/settings", json=payload,
                     headers=_auth_headers(admin_token), timeout=15)
    assert r.status_code == 200, f"failed to prime settings: {r.status_code} {r.text}"


# ---------------------------- Tests ----------------------------
# --- referrals/me -----------------------------------------------------
class TestReferralsMe:
    def test_authenticated_returns_code_and_stats(self):
        email = _rand_email("owner")
        reg = _register(email, name="Owner")
        assert reg["status"] == 200, reg
        token = reg["json"]["session_token"]

        r = _referral_me(token)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data.get("code"), str) and len(data["code"]) == 6, data
        assert data["code"].isalnum() and data["code"].upper() == data["code"]
        assert data["invited_count"] == 0
        assert data["rewarded_count"] == 0
        assert data["points_earned"] == 0
        assert data["reward_points"] == 100
        assert data["friend_discount_label"] == "10% off"
        assert data["can_redeem"] is True  # brand-new account, not referred, no orders

    def test_code_is_stable_across_calls(self):
        email = _rand_email("stable")
        reg = _register(email)
        token = reg["json"]["session_token"]
        c1 = _referral_me(token).json()["code"]
        c2 = _referral_me(token).json()["code"]
        assert c1 == c2

    def test_guest_forbidden(self):
        # No auth header at all
        r = requests.get(f"{API}/referrals/me", timeout=15)
        assert r.status_code in (401, 403), r.text


# --- register with referral_code -------------------------------------
class TestRegisterWithReferral:
    def test_valid_code_links_referral(self):
        # Referrer
        r_ref = _register(_rand_email("R"), name="Referrer")
        assert r_ref["status"] == 200
        ref_token = r_ref["json"]["session_token"]
        code = _referral_me(ref_token).json()["code"]

        # Friend registers WITH the code
        r_fr = _register(_rand_email("F"), name="Friend", referral_code=code)
        assert r_fr["status"] == 200, r_fr

        # Referrer stats should now show invited_count=1
        ref_me = _referral_me(ref_token).json()
        assert ref_me["invited_count"] == 1
        assert ref_me["rewarded_count"] == 0

    def test_invalid_code_registration_still_succeeds(self):
        r = _register(_rand_email("bad"), name="Bad", referral_code="ZZZZZZ")
        assert r["status"] == 200, r
        token = r["json"]["session_token"]
        me = _me(token)
        assert not me.get("referred_by")

    def test_no_code_field_works(self):
        r = _register(_rand_email("nocode"), name="NoCode")
        assert r["status"] == 200

    def test_partial_unique_index_allows_many_signups(self):
        """Regression: multiple signups produce many users w/ NULL referral_code
        until they visit /referrals/me. The partial unique index must allow this."""
        for _ in range(3):
            r = _register(_rand_email("bulk"))
            assert r["status"] == 200, r


# --- referrals/redeem -----------------------------------------------
class TestReferralsRedeem:
    def _make_referrer(self):
        r = _register(_rand_email("R2"))
        token = r["json"]["session_token"]
        code = _referral_me(token).json()["code"]
        return token, code

    def test_redeem_valid(self):
        _rt, code = self._make_referrer()
        r_fr = _register(_rand_email("Fx"))
        friend_token = r_fr["json"]["session_token"]
        r = requests.post(f"{API}/referrals/redeem", json={"code": code},
                          headers=_auth_headers(friend_token), timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert "10%" in body.get("friend_discount_label", "")

    def test_redeem_invalid_code(self):
        r_fr = _register(_rand_email("Fy"))
        friend_token = r_fr["json"]["session_token"]
        r = requests.post(f"{API}/referrals/redeem", json={"code": "NOPE99"},
                          headers=_auth_headers(friend_token), timeout=15)
        assert r.status_code == 400, r.text

    def test_redeem_self_referral(self):
        r = _register(_rand_email("self"))
        token = r["json"]["session_token"]
        own_code = _referral_me(token).json()["code"]
        r2 = requests.post(f"{API}/referrals/redeem", json={"code": own_code},
                           headers=_auth_headers(token), timeout=15)
        assert r2.status_code == 400, r2.text

    def test_redeem_already_referred(self):
        _rt, code = self._make_referrer()
        r_fr = _register(_rand_email("Fz"), referral_code=code)
        friend_token = r_fr["json"]["session_token"]
        # Try to redeem another code — should fail (already referred)
        _rt2, other_code = self._make_referrer()
        r = requests.post(f"{API}/referrals/redeem", json={"code": other_code},
                          headers=_auth_headers(friend_token), timeout=15)
        assert r.status_code == 400, r.text


# --- quote & order discount -----------------------------------------
class TestFriendDiscount:
    def test_quote_referred_user_gets_discount(self, orderable_item):
        r_ref = _register(_rand_email("Rq"))
        code = _referral_me(r_ref["json"]["session_token"]).json()["code"]
        r_fr = _register(_rand_email("Fq"), referral_code=code)
        ft = r_fr["json"]["session_token"]

        q = requests.post(f"{API}/orders/quote",
                          json=_order_body(orderable_item["item_id"], "cod"),
                          headers=_auth_headers(ft), timeout=20)
        assert q.status_code == 200, q.text
        body = q.json()
        subtotal = body["subtotal_cents"]
        assert subtotal > 0
        # 10% of subtotal expected (integer division)
        expected = subtotal * 10 // 100
        assert body["discount_cents"] == expected, body

    def test_quote_non_referred_user_no_discount(self, orderable_item):
        r_fr = _register(_rand_email("nonref"))
        ft = r_fr["json"]["session_token"]
        q = requests.post(f"{API}/orders/quote",
                          json=_order_body(orderable_item["item_id"], "cod"),
                          headers=_auth_headers(ft), timeout=20)
        assert q.status_code == 200, q.text
        assert q.json()["discount_cents"] == 0

    def test_cod_order_reflects_friend_discount(self, orderable_item):
        r_ref = _register(_rand_email("Rc"))
        code = _referral_me(r_ref["json"]["session_token"]).json()["code"]
        r_fr = _register(_rand_email("Fc"), referral_code=code)
        ft = r_fr["json"]["session_token"]
        o = requests.post(f"{API}/orders",
                          json=_order_body(orderable_item["item_id"], "cod"),
                          headers=_auth_headers(ft), timeout=25)
        assert o.status_code == 200, o.text
        body = o.json()
        # Response is the created Order object (has subtotal_cents/discount_cents)
        assert body.get("discount_cents", 0) > 0, body


# --- referrer reward + idempotency ----------------------------------
class TestReferrerReward:
    def test_reward_on_friends_first_paid_cod_order(self, orderable_item):
        r_ref = _register(_rand_email("Rr"))
        rt = r_ref["json"]["session_token"]
        # loyalty_points at start
        pre = _me(rt).get("loyalty_points", 0)
        code = _referral_me(rt).json()["code"]

        r_fr = _register(_rand_email("Fr"), referral_code=code)
        ft = r_fr["json"]["session_token"]
        o = requests.post(f"{API}/orders",
                          json=_order_body(orderable_item["item_id"], "cod"),
                          headers=_auth_headers(ft), timeout=25)
        assert o.status_code == 200, o.text

        # Small wait for any async writes to flush; the reward is awaited inline
        # but referrer stats read from db.
        time.sleep(1.0)
        post = _me(rt).get("loyalty_points", 0)
        assert post - pre == 100, f"expected +100, got pre={pre} post={post}"

        stats = _referral_me(rt).json()
        assert stats["rewarded_count"] == 1
        assert stats["points_earned"] == 100

    def test_reward_is_idempotent_on_second_order(self, orderable_item):
        r_ref = _register(_rand_email("Ri"))
        rt = r_ref["json"]["session_token"]
        code = _referral_me(rt).json()["code"]

        r_fr = _register(_rand_email("Fi"), referral_code=code)
        ft = r_fr["json"]["session_token"]
        # first order → reward
        o1 = requests.post(f"{API}/orders",
                           json=_order_body(orderable_item["item_id"], "cod"),
                           headers=_auth_headers(ft), timeout=25)
        assert o1.status_code == 200, o1.text
        time.sleep(1.0)
        pts_after_first = _me(rt).get("loyalty_points", 0)

        # second order by same friend → must NOT re-reward
        o2 = requests.post(f"{API}/orders",
                           json=_order_body(orderable_item["item_id"], "cod"),
                           headers=_auth_headers(ft), timeout=25)
        assert o2.status_code == 200, o2.text
        time.sleep(1.0)
        pts_after_second = _me(rt).get("loyalty_points", 0)
        assert pts_after_second == pts_after_first, (
            f"referrer got re-rewarded: {pts_after_first} → {pts_after_second}")

        stats = _referral_me(rt).json()
        assert stats["rewarded_count"] == 1


# --- redeem: already-ordered edge case --------------------------------
class TestRedeemAlreadyOrdered:
    def test_redeem_rejected_after_first_order(self, orderable_item):
        # User places a COD order (no referral), THEN tries to redeem a code.
        r_u = _register(_rand_email("uo"))
        ut = r_u["json"]["session_token"]
        # place order
        o = requests.post(f"{API}/orders",
                          json=_order_body(orderable_item["item_id"], "cod"),
                          headers=_auth_headers(ut), timeout=25)
        assert o.status_code == 200, o.text

        # a valid code from a fresh referrer
        rr = _register(_rand_email("ro2"))
        code = _referral_me(rr["json"]["session_token"]).json()["code"]

        r = requests.post(f"{API}/referrals/redeem", json={"code": code},
                          headers=_auth_headers(ut), timeout=15)
        assert r.status_code == 400, r.text


# --- admin settings persistence + toggle off --------------------------
class TestAdminSettings:
    def test_put_persists_referral_fields(self, admin_token, original_settings):
        payload = dict(original_settings)
        payload["referral_enabled"] = True
        payload["referral_reward_points"] = 250
        payload["referral_friend_discount_type"] = "fixed"
        payload["referral_friend_discount_value"] = 500  # $5.00
        payload.pop("_id", None)
        payload.pop("key", None)

        r = requests.put(f"{API}/admin/settings", json=payload,
                         headers=_auth_headers(admin_token), timeout=15)
        assert r.status_code == 200, r.text
        got = requests.get(f"{API}/admin/settings",
                           headers=_auth_headers(admin_token), timeout=15).json()
        assert got["referral_reward_points"] == 250
        assert got["referral_friend_discount_type"] == "fixed"
        assert got["referral_friend_discount_value"] == 500
        assert got["referral_enabled"] is True

        # Public /settings also exposes them (customer app reads them)
        pub = requests.get(f"{API}/settings", timeout=15).json()
        assert pub["referral_reward_points"] == 250
        assert pub["referral_friend_discount_type"] == "fixed"
        assert pub["referral_friend_discount_value"] == 500

        # And /referrals/me reflects the label
        u = _register(_rand_email("labelcheck"))
        rm = _referral_me(u["json"]["session_token"]).json()
        assert rm["friend_discount_label"] == "$5.00 off"

    def test_disabled_program_skips_discount_and_reward(
            self, admin_token, original_settings, orderable_item):
        # 1) Disable referrals
        payload = dict(original_settings)
        payload["referral_enabled"] = False
        payload["referral_reward_points"] = 100
        payload["referral_friend_discount_type"] = "percent"
        payload["referral_friend_discount_value"] = 10
        payload.pop("_id", None)
        payload.pop("key", None)
        r = requests.put(f"{API}/admin/settings", json=payload,
                         headers=_auth_headers(admin_token), timeout=15)
        assert r.status_code == 200

        try:
            r_ref = _register(_rand_email("Rd"))
            rt = r_ref["json"]["session_token"]
            pre_pts = _me(rt).get("loyalty_points", 0)
            code = _referral_me(rt).json()["code"]

            r_fr = _register(_rand_email("Fd"), referral_code=code)
            ft = r_fr["json"]["session_token"]

            # Quote: no referral discount
            q = requests.post(f"{API}/orders/quote",
                              json=_order_body(orderable_item["item_id"], "cod"),
                              headers=_auth_headers(ft), timeout=20)
            assert q.status_code == 200, q.text
            assert q.json()["discount_cents"] == 0, q.json()

            # Order: no reward on referrer
            o = requests.post(f"{API}/orders",
                              json=_order_body(orderable_item["item_id"], "cod"),
                              headers=_auth_headers(ft), timeout=25)
            assert o.status_code == 200, o.text
            time.sleep(1.0)
            post_pts = _me(rt).get("loyalty_points", 0)
            assert post_pts == pre_pts, (
                f"referrer earned points despite disabled program: {pre_pts} → {post_pts}")
        finally:
            # Re-enable
            payload["referral_enabled"] = True
            requests.put(f"{API}/admin/settings", json=payload,
                         headers=_auth_headers(admin_token), timeout=15)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
