"""
Backend tests for Delivery Partner App + Admin Delivery + Google Maps route optimization.

Covers:
  1. Google Maps helpers via /api/delivery/route (Directions + Geocoding + persist)
  2. Admin delivery partner CRUD (/api/admin/delivery-partners)
  3. Order assignment (/api/admin/orders/{id}/assign)
  4. Delivery partner auth (/api/delivery/login, /me, deactivation → 403)
  5. Delivery partner endpoints (/api/delivery/orders, /location, /status, /route)
  6. Customer tracking (/api/orders/{id}/tracking)
"""
import os
import time
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL", "")).rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@curryandco.local"
ADMIN_PASSWORD = "curry@admin2026"
DEMO_DP_EMAIL = "delivery@curryandco.local"
DEMO_DP_PASSWORD = "curry@delivery2026"


# ---------- shared fixtures ----------
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


@pytest.fixture(scope="module")
def guest_token(client):
    r = client.post(f"{API}/auth/guest")
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


@pytest.fixture(scope="module")
def guest_hdr(guest_token):
    return {"Authorization": f"Bearer {guest_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def guest_token_b(client):
    r = client.post(f"{API}/auth/guest")
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


@pytest.fixture(scope="module")
def guest_hdr_b(guest_token_b):
    return {"Authorization": f"Bearer {guest_token_b}", "Content-Type": "application/json"}


# ---------- helpers ----------
def _addr(line1="290 Bremner Blvd", city="Toronto", province="ON", postal="M5V 3L9"):
    return {"line1": line1, "city": city, "province": province, "postal_code": postal}


def _slot():
    return {"date": "2026-02-06", "window": "friday_evening"}


def _create_cod_order(client, hdr, current_menu, addr=None):
    """Create a real order via customer using COD (so it is immediately confirmed)."""
    item_id = current_menu["items"][0]["item_id"]
    body = {
        "items": [{"kind": "menu", "ref_id": item_id, "quantity": 1}],
        "address": addr or _addr(),
        "slot": _slot(),
        "phone": "+1 416-555-0100",
        "payment_method": "cod",
    }
    r = client.post(f"{API}/orders", json=body, headers=hdr)
    assert r.status_code == 200, r.text
    o = r.json()
    return o["order_id"], o


@pytest.fixture(scope="module")
def current_menu(client, seeded):
    r = client.get(f"{API}/menu/current")
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def reactivate_demo_partner(client, admin_hdr, seeded):
    """Ensure the seeded demo partner is active (previous test runs may have paused it)."""
    r = client.get(f"{API}/admin/delivery-partners", headers=admin_hdr)
    assert r.status_code == 200
    for p in r.json():
        if p["email"] == DEMO_DP_EMAIL:
            if not p.get("is_active", True):
                client.patch(f"{API}/admin/delivery-partners/{p['partner_id']}",
                             json={"is_active": True, "password": DEMO_DP_PASSWORD},
                             headers=admin_hdr)
            else:
                # Reset password to known value in case a prior test changed it.
                client.patch(f"{API}/admin/delivery-partners/{p['partner_id']}",
                             json={"password": DEMO_DP_PASSWORD},
                             headers=admin_hdr)
            return p["partner_id"]
    raise AssertionError("Demo delivery partner not seeded")


@pytest.fixture(scope="module")
def dp_token(client, reactivate_demo_partner):
    r = client.post(f"{API}/delivery/login",
                    json={"email": DEMO_DP_EMAIL, "password": DEMO_DP_PASSWORD})
    assert r.status_code == 200, r.text
    j = r.json()
    return j["access_token"]


@pytest.fixture(scope="module")
def dp_hdr(dp_token):
    return {"Authorization": f"Bearer {dp_token}", "Content-Type": "application/json"}


# ==========================================================
# 1. Delivery partner AUTH
# ==========================================================
class TestDeliveryAuth:
    def test_login_wrong_password(self, client, reactivate_demo_partner):
        r = client.post(f"{API}/delivery/login",
                        json={"email": DEMO_DP_EMAIL, "password": "wrong-pass"})
        assert r.status_code == 401

    def test_login_success(self, client, reactivate_demo_partner):
        r = client.post(f"{API}/delivery/login",
                        json={"email": DEMO_DP_EMAIL, "password": DEMO_DP_PASSWORD})
        assert r.status_code == 200, r.text
        j = r.json()
        assert "access_token" in j and j["token_type"] == "bearer"
        assert j["partner"]["email"] == DEMO_DP_EMAIL
        assert "password_hash" not in j["partner"]
        assert j["partner"]["name"] == "Rahul Das"

    def test_me_returns_partner(self, client, dp_hdr):
        r = client.get(f"{API}/delivery/me", headers=dp_hdr)
        assert r.status_code == 200
        p = r.json()
        assert p["email"] == DEMO_DP_EMAIL
        assert "password_hash" not in p

    def test_me_without_token_401(self, client):
        r = client.get(f"{API}/delivery/me")
        assert r.status_code == 401

    def test_admin_token_rejected_on_delivery_endpoint(self, client, admin_hdr):
        r = client.get(f"{API}/delivery/me", headers=admin_hdr)
        # Admin token has role="admin", not "delivery_partner" → 403
        assert r.status_code == 403


# ==========================================================
# 2. Admin delivery partner CRUD
# ==========================================================
class TestAdminPartnerCRUD:
    """Create → GET (list) → Update → Delete (soft) partner lifecycle."""
    _created: dict = {}

    def test_create_partner(self, client, admin_hdr):
        ts = int(time.time() * 1000)
        email = f"test.driver+{ts}@curryandco.local"
        r = client.post(f"{API}/admin/delivery-partners",
                        json={"name": "TEST Driver", "email": email,
                              "phone": "+1 416-555-0199", "vehicle": "bike",
                              "password": "Test1234!"},
                        headers=admin_hdr)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True
        p = j["partner"]
        assert p["email"] == email
        assert "password_hash" not in p
        assert p["is_active"] is True
        TestAdminPartnerCRUD._created["id"] = p["partner_id"]
        TestAdminPartnerCRUD._created["email"] = email

    def test_create_duplicate_email_409(self, client, admin_hdr):
        email = TestAdminPartnerCRUD._created["email"]
        r = client.post(f"{API}/admin/delivery-partners",
                        json={"name": "Dup", "email": email, "phone": "",
                              "vehicle": "car", "password": "x"},
                        headers=admin_hdr)
        assert r.status_code == 409

    def test_list_partners_has_active_orders_count(self, client, admin_hdr):
        r = client.get(f"{API}/admin/delivery-partners", headers=admin_hdr)
        assert r.status_code == 200
        arr = r.json()
        assert isinstance(arr, list) and len(arr) >= 1
        for p in arr:
            assert "active_orders" in p
            assert isinstance(p["active_orders"], int)
            assert "password_hash" not in p

    def test_update_partner_fields(self, client, admin_hdr):
        pid = TestAdminPartnerCRUD._created["id"]
        r = client.patch(f"{API}/admin/delivery-partners/{pid}",
                         json={"phone": "+1 416-000-9999", "vehicle": "scooter"},
                         headers=admin_hdr)
        assert r.status_code == 200, r.text
        p = r.json()["partner"]
        assert p["phone"] == "+1 416-000-9999"
        assert p["vehicle"] == "scooter"

    def test_update_password_and_login(self, client, admin_hdr):
        pid = TestAdminPartnerCRUD._created["id"]
        email = TestAdminPartnerCRUD._created["email"]
        r = client.patch(f"{API}/admin/delivery-partners/{pid}",
                         json={"password": "NewPass1!"}, headers=admin_hdr)
        assert r.status_code == 200
        r2 = client.post(f"{API}/delivery/login",
                         json={"email": email, "password": "NewPass1!"})
        assert r2.status_code == 200
        # Old password no longer works
        r3 = client.post(f"{API}/delivery/login",
                         json={"email": email, "password": "Test1234!"})
        assert r3.status_code == 401

    def test_deactivated_partner_cannot_login(self, client, admin_hdr):
        pid = TestAdminPartnerCRUD._created["id"]
        email = TestAdminPartnerCRUD._created["email"]
        # Get a fresh token first so we can also verify existing token stops working (403).
        r_login = client.post(f"{API}/delivery/login",
                              json={"email": email, "password": "NewPass1!"})
        assert r_login.status_code == 200
        old_token = r_login.json()["access_token"]

        r = client.patch(f"{API}/admin/delivery-partners/{pid}",
                         json={"is_active": False}, headers=admin_hdr)
        assert r.status_code == 200
        # Login blocked
        r2 = client.post(f"{API}/delivery/login",
                         json={"email": email, "password": "NewPass1!"})
        assert r2.status_code == 401
        # Existing token → 403 because _current_partner checks is_active
        r3 = client.get(f"{API}/delivery/me",
                        headers={"Authorization": f"Bearer {old_token}"})
        assert r3.status_code == 403

    def test_delete_soft_deactivates(self, client, admin_hdr):
        pid = TestAdminPartnerCRUD._created["id"]
        r = client.delete(f"{API}/admin/delivery-partners/{pid}", headers=admin_hdr)
        assert r.status_code == 200
        # After delete, list still contains it but is_active=False
        r2 = client.get(f"{API}/admin/delivery-partners", headers=admin_hdr)
        found = [p for p in r2.json() if p["partner_id"] == pid]
        assert len(found) == 1
        assert found[0]["is_active"] is False


# ==========================================================
# 3. Order assignment
# ==========================================================
class TestOrderAssignment:
    def test_assign_order_to_partner(self, client, admin_hdr, guest_hdr, current_menu,
                                     reactivate_demo_partner):
        order_id, _ = _create_cod_order(client, guest_hdr, current_menu)
        r = client.post(f"{API}/admin/orders/{order_id}/assign",
                        json={"partner_id": reactivate_demo_partner},
                        headers=admin_hdr)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True and j["assigned_to"] == reactivate_demo_partner

        # Verify via owner fetch (GET /admin/orders/{id} doesn't exist, use owner endpoint)
        r2 = client.get(f"{API}/orders/{order_id}", headers=guest_hdr)
        assert r2.status_code == 200
        o = r2.json()
        assert o["delivery_partner_id"] == reactivate_demo_partner
        assert o["delivery_status"] == "assigned"
        assert o["delivery_partner_name"] == "Rahul Das"
        # Order status should be "preparing" (from confirmed -> preparing)
        assert o["status"] == "preparing"
        # Tracking event appended
        events = [e.get("event") for e in o.get("tracking_events", []) if "event" in e]
        assert "assigned_to_partner" in events

    def test_assign_inactive_partner_404(self, client, admin_hdr, guest_hdr, current_menu):
        order_id, _ = _create_cod_order(client, guest_hdr, current_menu)
        # Create a partner and deactivate
        ts = int(time.time() * 1000)
        rc = client.post(f"{API}/admin/delivery-partners",
                         json={"name": "TEST Inactive", "email": f"inact+{ts}@curryandco.local",
                               "phone": "", "vehicle": "car", "password": "x1"},
                         headers=admin_hdr)
        assert rc.status_code == 200
        pid = rc.json()["partner"]["partner_id"]
        client.patch(f"{API}/admin/delivery-partners/{pid}",
                     json={"is_active": False}, headers=admin_hdr)
        r = client.post(f"{API}/admin/orders/{order_id}/assign",
                        json={"partner_id": pid}, headers=admin_hdr)
        assert r.status_code == 404

    def test_unassign_preserves_status(self, client, admin_hdr, guest_hdr, current_menu,
                                       reactivate_demo_partner):
        order_id, _ = _create_cod_order(client, guest_hdr, current_menu)
        # First assign (this may promote status to preparing)
        r0 = client.post(f"{API}/admin/orders/{order_id}/assign",
                         json={"partner_id": reactivate_demo_partner},
                         headers=admin_hdr)
        assert r0.status_code == 200
        # Fetch current status
        o_before = client.get(f"{API}/orders/{order_id}", headers=guest_hdr).json()
        status_before = o_before["status"]
        # Now unassign
        r = client.post(f"{API}/admin/orders/{order_id}/assign",
                        json={"partner_id": None}, headers=admin_hdr)
        assert r.status_code == 200
        assert r.json().get("unassigned") is True
        o_after = client.get(f"{API}/orders/{order_id}", headers=guest_hdr).json()
        assert o_after["delivery_partner_id"] is None
        assert o_after["delivery_status"] is None
        # Order status preserved (not reset)
        assert o_after["status"] == status_before


# ==========================================================
# 4. Delivery partner order endpoints
# ==========================================================
class TestDeliveryPartnerEndpoints:
    """Full lifecycle: assign → list active → status transitions → tracking."""

    @pytest.fixture(scope="class")
    def assigned_order(self, client, admin_hdr, guest_hdr, current_menu, reactivate_demo_partner):
        order_id, _ = _create_cod_order(client, guest_hdr, current_menu)
        r = client.post(f"{API}/admin/orders/{order_id}/assign",
                        json={"partner_id": reactivate_demo_partner},
                        headers=admin_hdr)
        assert r.status_code == 200
        return order_id

    def test_list_active_orders(self, client, dp_hdr, assigned_order):
        r = client.get(f"{API}/delivery/orders?status=active", headers=dp_hdr)
        assert r.status_code == 200
        orders = r.json()
        assert isinstance(orders, list)
        ids = [o["order_id"] for o in orders]
        assert assigned_order in ids
        # All returned must be assigned to this partner and in active statuses
        for o in orders:
            assert o["delivery_status"] in ("assigned", "picked_up", "on_the_way", "arrived")

    def test_reject_unknown_status(self, client, dp_hdr, assigned_order):
        r = client.post(f"{API}/delivery/orders/{assigned_order}/status",
                        json={"status": "levitating"}, headers=dp_hdr)
        assert r.status_code == 400

    def test_reject_foreign_order(self, client, admin_hdr, guest_hdr, current_menu, dp_hdr):
        # Create an unassigned order, dp should not be able to update it
        order_id, _ = _create_cod_order(client, guest_hdr, current_menu)
        r = client.post(f"{API}/delivery/orders/{order_id}/status",
                        json={"status": "picked_up"}, headers=dp_hdr)
        assert r.status_code == 404

    def test_status_transitions(self, client, guest_hdr, dp_hdr, assigned_order):
        # assigned → picked_up (order status -> out_for_delivery)
        r = client.post(f"{API}/delivery/orders/{assigned_order}/status",
                        json={"status": "picked_up"}, headers=dp_hdr)
        assert r.status_code == 200
        o = client.get(f"{API}/orders/{assigned_order}", headers=guest_hdr).json()
        assert o["delivery_status"] == "picked_up"
        assert o["status"] == "out_for_delivery"

        # picked_up → on_the_way (still out_for_delivery)
        r = client.post(f"{API}/delivery/orders/{assigned_order}/status",
                        json={"status": "on_the_way"}, headers=dp_hdr)
        assert r.status_code == 200
        o = client.get(f"{API}/orders/{assigned_order}", headers=guest_hdr).json()
        assert o["delivery_status"] == "on_the_way"
        assert o["status"] == "out_for_delivery"

        # on_the_way → arrived (status still out_for_delivery / not delivered yet)
        r = client.post(f"{API}/delivery/orders/{assigned_order}/status",
                        json={"status": "arrived"}, headers=dp_hdr)
        assert r.status_code == 200
        o = client.get(f"{API}/orders/{assigned_order}", headers=guest_hdr).json()
        assert o["delivery_status"] == "arrived"

        # arrived → delivered (status -> delivered, eta_seconds → 0)
        r = client.post(f"{API}/delivery/orders/{assigned_order}/status",
                        json={"status": "delivered"}, headers=dp_hdr)
        assert r.status_code == 200
        o = client.get(f"{API}/orders/{assigned_order}", headers=guest_hdr).json()
        assert o["delivery_status"] == "delivered"
        assert o["status"] == "delivered"
        assert o.get("delivery_eta_seconds") == 0

    def test_location_fan_out(self, client, admin_hdr, guest_hdr, current_menu, dp_hdr,
                              reactivate_demo_partner):
        # Set up a fresh active (picked_up) order so location fan-out targets it
        order_id, _ = _create_cod_order(client, guest_hdr, current_menu)
        client.post(f"{API}/admin/orders/{order_id}/assign",
                    json={"partner_id": reactivate_demo_partner}, headers=admin_hdr)
        client.post(f"{API}/delivery/orders/{order_id}/status",
                    json={"status": "picked_up"}, headers=dp_hdr)

        r = client.post(f"{API}/delivery/location",
                        json={"lat": 43.6532, "lng": -79.3832}, headers=dp_hdr)
        assert r.status_code == 200

        # /delivery/me should have current_lat/lng
        me = client.get(f"{API}/delivery/me", headers=dp_hdr).json()
        assert me.get("current_lat") == 43.6532
        assert me.get("current_lng") == -79.3832

        # The active order should have received the fan-out
        o = client.get(f"{API}/orders/{order_id}", headers=guest_hdr).json()
        assert o.get("delivery_partner_lat") == 43.6532
        assert o.get("delivery_partner_lng") == -79.3832


# ==========================================================
# 5. Google Maps route optimization (real API)
# ==========================================================
class TestGoogleRoute:
    """Uses live Google Maps API. Verifies geocoding + directions optimize."""

    def test_route_optimize_and_persist(self, client, admin_hdr, guest_hdr, current_menu,
                                        dp_hdr, reactivate_demo_partner):
        # 3 real Toronto addresses to hit geocoding path (persistence)
        addresses = [
            _addr("290 Bremner Blvd", "Toronto", "ON", "M5V 3L9"),   # CN Tower area
            _addr("1 Blue Jays Way", "Toronto", "ON", "M5V 1J1"),   # Rogers Centre
            _addr("100 Queens Park", "Toronto", "ON", "M5S 2C6"),   # ROM
        ]
        order_ids = []
        for a in addresses:
            oid, _ = _create_cod_order(client, guest_hdr, current_menu, addr=a)
            r = client.post(f"{API}/admin/orders/{oid}/assign",
                            json={"partner_id": reactivate_demo_partner}, headers=admin_hdr)
            assert r.status_code == 200
            order_ids.append(oid)

        # Origin: Union Station
        r = client.post(f"{API}/delivery/route",
                        json={"origin_lat": 43.6453, "origin_lng": -79.3806,
                              "order_ids": order_ids}, headers=dp_hdr, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True
        # If optimized True → real Google response
        assert "optimized" in j
        assert isinstance(j["stops"], list) and len(j["stops"]) == 3
        for s in j["stops"]:
            assert s["order_id"] in order_ids
            assert isinstance(s["route_index"], int)
            assert s["eta_seconds"] >= 0
            assert isinstance(s["lat"], (int, float))
            assert isinstance(s["lng"], (int, float))
            assert s["address"]

        # Route indexes are 0..N-1 and unique
        idxs = sorted(s["route_index"] for s in j["stops"])
        assert idxs == list(range(len(idxs)))

        if j["optimized"]:
            # Real Google → polyline present
            assert j.get("polyline")
            assert j["total_duration_sec"] > 0
        else:
            # Fallback path — still a valid contract
            assert j.get("note")

        # Persistence check: each order got delivery_route_order + delivery_eta_seconds
        for oid in order_ids:
            o = client.get(f"{API}/orders/{oid}", headers=guest_hdr).json()
            assert o.get("delivery_route_order") is not None
            assert o.get("delivery_eta_seconds") is not None

        # Also verify address got persisted with lat/lng (geocode side-effect)
        for oid in order_ids:
            o = client.get(f"{API}/orders/{oid}", headers=guest_hdr).json()
            addr = o.get("address") or {}
            assert addr.get("lat") is not None
            assert addr.get("lng") is not None

    def test_route_rejects_other_partners_orders(self, client, admin_hdr, guest_hdr,
                                                 current_menu, dp_hdr):
        # Order that's NOT assigned to this partner
        oid, _ = _create_cod_order(client, guest_hdr, current_menu)
        r = client.post(f"{API}/delivery/route",
                        json={"origin_lat": 43.6532, "origin_lng": -79.3832,
                              "order_ids": [oid]}, headers=dp_hdr, timeout=15)
        assert r.status_code == 404


# ==========================================================
# 6. Customer tracking endpoint
# ==========================================================
class TestCustomerTracking:
    def test_tracking_returns_partner_and_eta(self, client, admin_hdr, guest_hdr,
                                              current_menu, dp_hdr, reactivate_demo_partner):
        # Create order → assign → picked_up → location update
        oid, _ = _create_cod_order(client, guest_hdr, current_menu,
                                   addr=_addr("290 Bremner Blvd", "Toronto", "ON", "M5V 3L9"))
        client.post(f"{API}/admin/orders/{oid}/assign",
                    json={"partner_id": reactivate_demo_partner}, headers=admin_hdr)
        client.post(f"{API}/delivery/orders/{oid}/status",
                    json={"status": "picked_up"}, headers=dp_hdr)
        client.post(f"{API}/delivery/location",
                    json={"lat": 43.6600, "lng": -79.3900}, headers=dp_hdr)

        r = client.get(f"{API}/orders/{oid}/tracking", headers=guest_hdr)
        assert r.status_code == 200, r.text
        t = r.json()
        assert t["order_id"] == oid
        assert t["status"] == "out_for_delivery"
        assert t["delivery_status"] == "picked_up"
        assert t["delivery_partner"]["name"] == "Rahul Das"
        assert t["delivery_partner"]["phone"]
        assert t["partner_location"]["lat"] == 43.6600
        assert t["partner_location"]["lng"] == -79.3900
        # tracking_events limited to last 6
        assert isinstance(t["tracking_events"], list)
        assert len(t["tracking_events"]) <= 6

    def test_tracking_foreign_user_404(self, client, admin_hdr, guest_hdr, guest_hdr_b,
                                       current_menu, reactivate_demo_partner):
        # User A creates order; user B tries to fetch tracking → 404
        oid, _ = _create_cod_order(client, guest_hdr, current_menu)
        client.post(f"{API}/admin/orders/{oid}/assign",
                    json={"partner_id": reactivate_demo_partner}, headers=admin_hdr)
        r = client.get(f"{API}/orders/{oid}/tracking", headers=guest_hdr_b)
        assert r.status_code == 404


# ==========================================================
# 7. Regression: seeded demo partner is idempotent
# ==========================================================
class TestSeedIdempotency:
    def test_reseed_does_not_duplicate_demo_partner(self, client, admin_hdr):
        client.post(f"{API}/dev/seed", timeout=60)
        client.post(f"{API}/dev/seed", timeout=60)
        r = client.get(f"{API}/admin/delivery-partners", headers=admin_hdr)
        matches = [p for p in r.json() if p["email"] == DEMO_DP_EMAIL]
        assert len(matches) == 1
