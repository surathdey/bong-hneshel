"""
Backend tests for the new delivery geocoding endpoints (iteration 12):
  POST /api/delivery/geocode           {address} -> {lat, lng, formatted}
  POST /api/delivery/reverse-geocode   {lat, lng} -> {lat, lng, formatted}

Also regression-checks /api/delivery/route with values coming from these endpoints.

Auth: requires partner bearer (seeded demo delivery partner).
Uses LIVE Google Maps API (key configured in backend/.env).
"""
import os
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL", "")).rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL / EXPO_BACKEND_URL must be set"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@curryandco.local"
ADMIN_PASSWORD = "curry@admin2026"
DP_EMAIL = "delivery@curryandco.local"
DP_PASSWORD = "curry@delivery2026"


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
def admin_hdr(client, seeded):
    r = client.post(f"{API}/admin/login",
                    json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}",
            "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def dp_hdr(client, admin_hdr, seeded):
    # ensure seeded partner is active & password reset
    plist = client.get(f"{API}/admin/delivery-partners", headers=admin_hdr).json()
    for p in plist:
        if p["email"] == DP_EMAIL:
            client.patch(f"{API}/admin/delivery-partners/{p['partner_id']}",
                         json={"is_active": True, "password": DP_PASSWORD},
                         headers=admin_hdr)
            break
    r = client.post(f"{API}/delivery/login",
                    json={"email": DP_EMAIL, "password": DP_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}",
            "Content-Type": "application/json"}


# ==========================================================
# /api/delivery/geocode
# ==========================================================
class TestGeocode:
    def test_geocode_no_auth_401(self, client):
        r = client.post(f"{API}/delivery/geocode",
                        json={"address": "CN Tower, Toronto"})
        assert r.status_code == 401, r.text

    def test_geocode_valid_address(self, client, dp_hdr):
        r = client.post(f"{API}/delivery/geocode",
                        json={"address": "CN Tower, Toronto"}, headers=dp_hdr,
                        timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "lat" in j and "lng" in j and "formatted" in j
        assert isinstance(j["lat"], (int, float))
        assert isinstance(j["lng"], (int, float))
        # CN Tower is ~43.6426 N, -79.3871 W — allow +/- 0.05° tolerance
        assert 43.60 <= j["lat"] <= 43.70, f"unexpected lat: {j['lat']}"
        assert -79.42 <= j["lng"] <= -79.35, f"unexpected lng: {j['lng']}"
        # Google usually returns a Bremner Blvd address
        assert "Toronto" in j["formatted"]

    def test_geocode_empty_400(self, client, dp_hdr):
        r = client.post(f"{API}/delivery/geocode",
                        json={"address": ""}, headers=dp_hdr)
        assert r.status_code == 400, r.text

    def test_geocode_whitespace_400(self, client, dp_hdr):
        r = client.post(f"{API}/delivery/geocode",
                        json={"address": "   "}, headers=dp_hdr)
        assert r.status_code == 400, r.text

    def test_geocode_missing_field_422(self, client, dp_hdr):
        # Pydantic rejects missing required field with 422
        r = client.post(f"{API}/delivery/geocode",
                        json={}, headers=dp_hdr)
        assert r.status_code in (400, 422), r.text

    def test_geocode_nonsense_404(self, client, dp_hdr):
        r = client.post(f"{API}/delivery/geocode",
                        json={"address": "asldkfjalsdkjqwzxpqoiweuxjvzxcv"},
                        headers=dp_hdr, timeout=15)
        assert r.status_code == 404, r.text
        assert "geocode" in r.json().get("detail", "").lower() or \
               "could not" in r.json().get("detail", "").lower()


# ==========================================================
# /api/delivery/reverse-geocode
# ==========================================================
class TestReverseGeocode:
    def test_reverse_no_auth_401(self, client):
        r = client.post(f"{API}/delivery/reverse-geocode",
                        json={"lat": 43.6532, "lng": -79.3832})
        assert r.status_code == 401, r.text

    def test_reverse_valid(self, client, dp_hdr):
        r = client.post(f"{API}/delivery/reverse-geocode",
                        json={"lat": 43.6532, "lng": -79.3832},
                        headers=dp_hdr, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["lat"] == 43.6532
        assert j["lng"] == -79.3832
        assert "formatted" in j
        assert "Toronto" in j["formatted"] or "ON" in j["formatted"] \
            or "Canada" in j["formatted"]

    def test_reverse_out_of_bounds_404(self, client, dp_hdr):
        # (0,0) is in the ocean — Google returns ZERO_RESULTS
        r = client.post(f"{API}/delivery/reverse-geocode",
                        json={"lat": 0, "lng": 0}, headers=dp_hdr, timeout=15)
        assert r.status_code == 404, r.text

    def test_reverse_missing_field_422(self, client, dp_hdr):
        r = client.post(f"{API}/delivery/reverse-geocode",
                        json={"lat": 43.65}, headers=dp_hdr)
        assert r.status_code in (400, 422), r.text


# ==========================================================
# Regression: /api/delivery/route with lat/lng from geocode
# ==========================================================
class TestRouteRegression:
    def test_route_with_geocoded_origin(self, client, dp_hdr, admin_hdr):
        # 1. Geocode "Union Station, Toronto"
        g = client.post(f"{API}/delivery/geocode",
                        json={"address": "Union Station, Toronto"},
                        headers=dp_hdr, timeout=15)
        assert g.status_code == 200, g.text
        lat, lng = g.json()["lat"], g.json()["lng"]

        # 2. Fetch this partner's active orders (seeded assignments exist)
        orders = client.get(f"{API}/delivery/orders?status=active",
                            headers=dp_hdr).json()
        if not orders:
            pytest.skip("no assigned orders — cannot regress route")
        order_ids = [o["order_id"] for o in orders[:3]]  # cap at 3 for speed

        # 3. Call /delivery/route with those coords
        r = client.post(f"{API}/delivery/route",
                        json={"origin_lat": lat, "origin_lng": lng,
                              "order_ids": order_ids},
                        headers=dp_hdr, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True
        assert isinstance(j["stops"], list) and len(j["stops"]) == len(order_ids)
        for s in j["stops"]:
            assert s["order_id"] in order_ids
            assert isinstance(s["lat"], (int, float))
            assert isinstance(s["lng"], (int, float))
