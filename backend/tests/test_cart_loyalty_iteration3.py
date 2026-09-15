"""
Iteration 3 backend tests for cart loyalty redemption in POST /api/orders/quote

Scope:
- Member (bearer=testmember-loyalty-2026, 500 pts) can redeem 300 pts → -$3 off
- Guest session cannot redeem (points_redeemed_cents must stay 0)
"""
import os
import pytest
import requests

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")

MEMBER_TOKEN = "testmember-loyalty-2026"
ITEM_ID = "mi_a7b61af064"  # $20 menu item

QUOTE_BODY = {
    "items": [{"kind": "menu", "ref_id": ITEM_ID, "quantity": 5}],
    "address": {"line1": "1 King St", "city": "Toronto", "postal_code": "M5H1A1"},
    "slot": {"date": "2026-09-20", "window": "saturday_morning"},
    "payment_method": "cod",
    "redeem_points": 300,
}


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# --- Member redemption path ---
class TestMemberRedeem:
    def test_member_quote_redeems_300_points(self, api):
        r = api.post(
            f"{BASE_URL}/api/orders/quote",
            json=QUOTE_BODY,
            headers={"Authorization": f"Bearer {MEMBER_TOKEN}"},
            timeout=30,
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text}"
        j = r.json()
        assert j["subtotal_cents"] == 10000, f"subtotal={j.get('subtotal_cents')}"
        assert j["points_redeemed_cents"] == 300, f"points_redeemed={j.get('points_redeemed_cents')}"
        assert j["points_available"] == 500, f"points_available={j.get('points_available')}"
        # total should be reduced by exactly 300 cents vs no-redeem
        no_redeem = {**QUOTE_BODY, "redeem_points": 0}
        r2 = api.post(
            f"{BASE_URL}/api/orders/quote",
            json=no_redeem,
            headers={"Authorization": f"Bearer {MEMBER_TOKEN}"},
            timeout=30,
        )
        assert r2.status_code == 200
        j2 = r2.json()
        assert j["total_cents"] == j2["total_cents"] - 300, (
            f"delta total mismatch: with={j['total_cents']} without={j2['total_cents']}"
        )


# --- Guest gating ---
class TestGuestGating:
    def test_guest_cannot_redeem(self, api):
        gr = api.post(f"{BASE_URL}/api/auth/guest", json={}, timeout=30)
        assert gr.status_code == 200, f"guest session failed: {gr.status_code} {gr.text}"
        gjson = gr.json()
        # possible token keys
        token = (
            gjson.get("session_token")
            or gjson.get("access_token")
            or gjson.get("token")
            or (gjson.get("session") or {}).get("session_token")
        )
        assert token, f"no token in guest response: {gjson}"

        r = api.post(
            f"{BASE_URL}/api/orders/quote",
            json=QUOTE_BODY,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text}"
        j = r.json()
        assert j["subtotal_cents"] == 10000
        assert j["points_redeemed_cents"] == 0, (
            f"guest should not redeem, got {j.get('points_redeemed_cents')}"
        )
