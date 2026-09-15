"""
Admin Coupons CRUD backend tests (iteration 7).
Covers:
- Admin login (access_token key)
- GET /api/admin/coupons list
- POST /api/admin/coupons create (percent + fixed)
- PUT /api/admin/coupons/{code} update (percent -> fixed)
- Toggle active via PUT
- DELETE /api/admin/coupons/{code}
- First-time-only enforcement (400 conflict when a first_time_only coupon is already active)
- Auth required (401 when missing/invalid bearer)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://clone-verify-2.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@bong-hneshel.ca"
ADMIN_PASSWORD = "DDuCi!dZ0UmN3vXu"
TEST_CODE = "TEST_ITER7"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/admin/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "access_token" in data, f"Login response missing access_token: {data}"
    assert data.get("token_type") == "bearer"
    return data["access_token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module", autouse=True)
def cleanup(auth_headers):
    # pre-clean any stale TEST_ITER7 coupon
    requests.delete(f"{BASE_URL}/api/admin/coupons/{TEST_CODE}", headers=auth_headers, timeout=15)
    yield
    # final cleanup
    requests.delete(f"{BASE_URL}/api/admin/coupons/{TEST_CODE}", headers=auth_headers, timeout=15)


# --- Auth guards ---
def test_list_requires_auth():
    r = requests.get(f"{BASE_URL}/api/admin/coupons", timeout=15)
    assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"


def test_create_requires_auth():
    r = requests.post(f"{BASE_URL}/api/admin/coupons",
                      json={"code": "X", "discount_type": "percent", "value": 10, "active": True,
                            "min_order_cents": 0, "description": "", "first_time_only": False},
                      timeout=15)
    assert r.status_code in (401, 403)


# --- List ---
def test_list_coupons(auth_headers):
    r = requests.get(f"{BASE_URL}/api/admin/coupons", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert "coupons" in data and isinstance(data["coupons"], list)
    codes = [c["code"] for c in data["coupons"]]
    # FIRST10 is seeded per problem statement
    assert "FIRST10" in codes, f"Expected FIRST10 in seeded coupons, got {codes}"
    first10 = next(c for c in data["coupons"] if c["code"] == "FIRST10")
    assert first10["active"] is True
    assert first10["first_time_only"] is True
    assert first10["discount_type"] == "percent"


# --- CRUD ---
def test_create_percent_coupon(auth_headers):
    payload = {
        "code": TEST_CODE, "discount_type": "percent", "value": 20,
        "active": True, "min_order_cents": 1000,
        "description": "TEST iter7 percent coupon", "first_time_only": False,
    }
    r = requests.post(f"{BASE_URL}/api/admin/coupons", headers=auth_headers, json=payload, timeout=15)
    assert r.status_code == 200, f"Create failed: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("ok") is True
    c = body["coupon"]
    assert c["code"] == TEST_CODE
    assert c["discount_type"] == "percent"
    assert c["value"] == 20
    assert c["min_order_cents"] == 1000
    assert c["active"] is True
    assert c["first_time_only"] is False

    # GET verify persistence
    lst = requests.get(f"{BASE_URL}/api/admin/coupons", headers=auth_headers, timeout=15).json()["coupons"]
    got = next((x for x in lst if x["code"] == TEST_CODE), None)
    assert got is not None, "Coupon not persisted"
    assert got["value"] == 20 and got["discount_type"] == "percent"


def test_update_to_fixed(auth_headers):
    payload = {
        "code": TEST_CODE, "discount_type": "fixed", "value": 500,
        "active": True, "min_order_cents": 1500,
        "description": "TEST iter7 fixed", "first_time_only": False,
    }
    r = requests.put(f"{BASE_URL}/api/admin/coupons/{TEST_CODE}", headers=auth_headers, json=payload, timeout=15)
    assert r.status_code == 200, r.text
    c = r.json()["coupon"]
    assert c["discount_type"] == "fixed"
    assert c["value"] == 500
    assert c["min_order_cents"] == 1500

    # GET verify
    lst = requests.get(f"{BASE_URL}/api/admin/coupons", headers=auth_headers, timeout=15).json()["coupons"]
    got = next(x for x in lst if x["code"] == TEST_CODE)
    assert got["discount_type"] == "fixed" and got["value"] == 500


def test_toggle_active(auth_headers):
    # deactivate
    payload = {
        "code": TEST_CODE, "discount_type": "fixed", "value": 500,
        "active": False, "min_order_cents": 1500,
        "description": "TEST iter7 fixed", "first_time_only": False,
    }
    r = requests.put(f"{BASE_URL}/api/admin/coupons/{TEST_CODE}", headers=auth_headers, json=payload, timeout=15)
    assert r.status_code == 200
    assert r.json()["coupon"]["active"] is False


def test_first_time_conflict_on_create(auth_headers):
    # Try to create a new active + first_time_only coupon while FIRST10 already claims that.
    conflict_code = "TEST_ITER7_FT"
    # Preclean if leftover
    requests.delete(f"{BASE_URL}/api/admin/coupons/{conflict_code}", headers=auth_headers, timeout=15)
    payload = {
        "code": conflict_code, "discount_type": "percent", "value": 15,
        "active": True, "min_order_cents": 0,
        "description": "conflict test", "first_time_only": True,
    }
    r = requests.post(f"{BASE_URL}/api/admin/coupons", headers=auth_headers, json=payload, timeout=15)
    assert r.status_code == 400, f"Expected 400 conflict, got {r.status_code} {r.text}"
    assert "first-time" in r.text.lower(), f"Error msg should mention first-time, got: {r.text}"
    # Verify NOT persisted
    lst = requests.get(f"{BASE_URL}/api/admin/coupons", headers=auth_headers, timeout=15).json()["coupons"]
    assert not any(x["code"] == conflict_code for x in lst), "Conflict coupon should not exist"


def test_first_time_conflict_on_update(auth_headers):
    # Try to toggle TEST_ITER7 to first_time_only=True while active -> conflict expected
    payload = {
        "code": TEST_CODE, "discount_type": "fixed", "value": 500,
        "active": True, "min_order_cents": 1500,
        "description": "TEST iter7", "first_time_only": True,
    }
    r = requests.put(f"{BASE_URL}/api/admin/coupons/{TEST_CODE}", headers=auth_headers, json=payload, timeout=15)
    assert r.status_code == 400
    assert "first-time" in r.text.lower()


def test_delete_coupon(auth_headers):
    r = requests.delete(f"{BASE_URL}/api/admin/coupons/{TEST_CODE}", headers=auth_headers, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True
    # GET verify 404 on subsequent delete
    r2 = requests.delete(f"{BASE_URL}/api/admin/coupons/{TEST_CODE}", headers=auth_headers, timeout=15)
    assert r2.status_code == 404
    # Not in list
    lst = requests.get(f"{BASE_URL}/api/admin/coupons", headers=auth_headers, timeout=15).json()["coupons"]
    assert not any(x["code"] == TEST_CODE for x in lst)


def test_code_uppercased_on_create(auth_headers):
    lower_code = "test_iter7_lc"
    payload = {
        "code": lower_code, "discount_type": "percent", "value": 5,
        "active": False, "min_order_cents": 0, "description": "", "first_time_only": False,
    }
    r = requests.post(f"{BASE_URL}/api/admin/coupons", headers=auth_headers, json=payload, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["coupon"]["code"] == lower_code.upper()
    # Cleanup
    requests.delete(f"{BASE_URL}/api/admin/coupons/{lower_code.upper()}", headers=auth_headers, timeout=15)
