"""
Backend tests for the new Delivery Policy feature (iteration 17):
  1. POST /api/orders/quote — tiered distance-based delivery fee
  2. POST /api/delivery/orders/{id}/proof — proof-of-delivery photo upload
  3. POST /api/delivery/orders/{id}/status {status:'delivered'} does NOT 500
     even without Emergent Email / Twilio configured (best-effort)
  4. GET /api/uploads/delivery/<file> returns the uploaded image publicly
"""
import io
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or \
           os.environ.get("EXPO_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "Backend URL env var required"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@mustardgarden.ca"
ADMIN_PASSWORD = "tlUYkZz1JnsD%Wy2"
DP_EMAIL = "rider@mustardgarden.ca"
DP_PASSWORD = "rider@2026"

# Real Toronto downtown ~60km driving from Milton kitchen -> should be 40–75 km
TORONTO_ADDR = {
    "line1": "290 Bremner Blvd", "city": "Toronto",
    "province": "ON", "postal_code": "M5V 3L9",
}
# Milton address near the kitchen -> should be 0–20 km FREE
MILTON_ADDR = {
    "line1": "6941 Derry Rd W", "city": "Milton",
    "province": "ON", "postal_code": "L9T 7H8",
}


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="module")
def admin_hdr(s):
    r = s.post(f"{API}/admin/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def dp_login(s):
    r = s.post(f"{API}/delivery/login",
               json={"email": DP_EMAIL, "password": DP_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    return j


@pytest.fixture(scope="module")
def dp_hdr(dp_login):
    return {"Authorization": f"Bearer {dp_login['access_token']}"}


@pytest.fixture(scope="module")
def guest_hdr(s):
    r = s.post(f"{API}/auth/guest", timeout=15)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}",
            "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def current_item_id(s):
    r = s.get(f"{API}/menu/current", timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["items"][0]["item_id"]


def _quote_body(addr, item_id):
    return {
        "items": [{"kind": "menu", "ref_id": item_id, "quantity": 1}],
        "address": addr,
        "slot": {"date": "2026-02-06", "window": "friday_evening"},
        "phone": "+1 416-555-0100",
    }


# ==========================================================
# 1. Distance-based delivery fee via /orders/quote
# ==========================================================
class TestDeliveryFeeQuote:
    def test_toronto_tier_40_75(self, s, guest_hdr, current_item_id):
        r = s.post(f"{API}/orders/quote",
                   json=_quote_body(TORONTO_ADDR, current_item_id),
                   headers=guest_hdr, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["delivery_fee_cents"] == 1000, f"expected 1000c, got {j.get('delivery_fee_cents')}"
        assert j["delivery_fee_tier"] == "40–75 km"
        assert j["delivery_time_window"] == "6:00 AM – 8:00 PM"
        assert "condo" in j["delivery_condo_policy"].lower()
        assert j["delivery_distance_km"] is not None
        assert 30 < j["delivery_distance_km"] < 90

    def test_milton_tier_free(self, s, guest_hdr, current_item_id):
        r = s.post(f"{API}/orders/quote",
                   json=_quote_body(MILTON_ADDR, current_item_id),
                   headers=guest_hdr, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["delivery_fee_cents"] == 0, f"expected FREE (0c), got {j.get('delivery_fee_cents')}"
        assert j["delivery_fee_tier"] == "0–20 km"
        assert j["delivery_distance_km"] is not None
        assert j["delivery_distance_km"] <= 20
        assert j["delivery_time_window"] == "6:00 AM – 8:00 PM"
        assert j["delivery_condo_policy"]


# ==========================================================
# 2 + 3 + 4. Proof upload + delivered notification best-effort + public URL
# ==========================================================
class TestProofAndDelivered:
    @pytest.fixture(scope="class")
    def rider_partner_id(self, s, admin_hdr):
        r = s.get(f"{API}/admin/delivery-partners", headers=admin_hdr, timeout=15)
        assert r.status_code == 200, r.text
        for p in r.json():
            if p["email"] == DP_EMAIL:
                return p["partner_id"]
        pytest.fail(f"rider partner {DP_EMAIL} not found")

    @pytest.fixture(scope="class")
    def assigned_order_id(self, s, admin_hdr, guest_hdr, current_item_id, rider_partner_id):
        # Create a COD order (immediately confirmed) with a Toronto address
        body = {
            "items": [{"kind": "menu", "ref_id": current_item_id, "quantity": 1}],
            "address": TORONTO_ADDR,
            "slot": {"date": "2026-02-06", "window": "friday_evening"},
            "phone": "+1 416-555-0100",
            "payment_method": "cod",
        }
        r = s.post(f"{API}/orders", json=body, headers=guest_hdr, timeout=30)
        assert r.status_code == 200, r.text
        oid = r.json()["order_id"]
        # Assign to rider
        ra = s.post(f"{API}/admin/orders/{oid}/assign",
                    json={"partner_id": rider_partner_id}, headers=admin_hdr, timeout=15)
        assert ra.status_code == 200, ra.text
        return oid

    def test_proof_upload_saves_and_persists_url(self, s, dp_hdr, assigned_order_id):
        # Minimal valid PNG (1x1 red pixel)
        png = bytes.fromhex(
            "89504E470D0A1A0A0000000D49484452000000010000000108020000009077"
            "3DDE0000000C4944415478DA6360F80F0000010101000E9DFCDD0000000049"
            "454E44AE426082"
        )
        files = {"photo": ("proof.png", io.BytesIO(png), "image/png")}
        # Use a fresh requests call — the shared session sets Content-Type: application/json
        # which breaks multipart uploads.
        hdr = {k: v for k, v in dp_hdr.items() if k.lower() == "authorization"}
        r = requests.post(f"{API}/delivery/orders/{assigned_order_id}/proof",
                          headers=hdr, files=files, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True
        url = j["delivery_proof_photo_url"]
        assert url.startswith("/api/uploads/delivery/")
        assert url.endswith(".png")

        # Public GET on the URL returns image bytes
        r2 = requests.get(f"{BASE_URL}{url}", timeout=15)
        assert r2.status_code == 200, r2.text
        assert r2.headers.get("content-type", "").startswith("image/"), r2.headers
        assert len(r2.content) >= len(png) - 4  # server may re-encode; loose check

        # Persistence: order should carry the proof url
        # (Reuse admin fetch via guest_hdr — the order belongs to guest)
        # Simplest is dp view of order via /delivery/orders?status=active or by
        # completing the flow below.

    def test_delivered_status_does_not_500_without_email_twilio(
        self, s, dp_hdr, assigned_order_id, guest_hdr
    ):
        # Advance to arrived first (optional — status endpoint accepts direct 'delivered'
        # from assigned. Test the actual /delivered call.)
        r_arr = s.post(f"{API}/delivery/orders/{assigned_order_id}/status",
                       json={"status": "arrived"},
                       headers={**dp_hdr, "Content-Type": "application/json"},
                       timeout=15)
        assert r_arr.status_code == 200, r_arr.text

        r = s.post(f"{API}/delivery/orders/{assigned_order_id}/status",
                   json={"status": "delivered"},
                   headers={**dp_hdr, "Content-Type": "application/json"},
                   timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True and j["status"] == "delivered"

        # Verify order.status == 'delivered' via customer GET
        r2 = s.get(f"{API}/orders/{assigned_order_id}", headers=guest_hdr, timeout=15)
        assert r2.status_code == 200, r2.text
        o = r2.json()
        assert o["status"] == "delivered"
        assert o["delivery_status"] == "delivered"
        assert o.get("delivery_proof_photo_url", "").startswith("/api/uploads/delivery/")
