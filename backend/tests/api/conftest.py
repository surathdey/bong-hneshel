"""
Shared pytest fixtures for the Bong Hneshel backend API test suite.

Run against a live backend (defaults to the local supervisor instance):
    BASE_URL=http://localhost:8001 pytest backend/tests/api -v

Override credentials / target with env vars:
    BASE_URL          base origin of the API (default http://localhost:8001)
    ADMIN_EMAIL       admin login email     (default admin@bong-hneshel.ca)
    ADMIN_PASSWORD    admin login password  (default from test_credentials.md)
"""
import os
import datetime as dt

import httpx
import pytest

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8001").rstrip("/")
API = BASE_URL + "/api"

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@bong-hneshel.ca")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "DDuCi!dZ0UmN3vXu")

TIMEOUT = float(os.environ.get("API_TIMEOUT", "30"))


@pytest.fixture(scope="session")
def api() -> str:
    """Base API URL, e.g. http://localhost:8001/api"""
    return API


@pytest.fixture(scope="session")
def client():
    """A plain httpx client (no auth) rooted at the /api prefix."""
    with httpx.Client(base_url=API, timeout=TIMEOUT) as c:
        yield c


@pytest.fixture(scope="session")
def admin_token():
    """Log in as admin and return the bearer access token."""
    r = httpx.post(
        f"{API}/admin/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        pytest.skip(f"admin login failed ({r.status_code}); check ADMIN_EMAIL/ADMIN_PASSWORD")
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def guest_session():
    """Create a guest account; returns {'session_token','user'}."""
    r = httpx.post(f"{API}/auth/guest", timeout=TIMEOUT)
    assert r.status_code == 200, f"guest auth failed: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="session")
def guest_headers(guest_session):
    return {"Authorization": f"Bearer {guest_session['session_token']}"}


def _next_friday_iso() -> str:
    today = dt.date.today()
    delta = (4 - today.weekday()) % 7  # Friday = 4
    delta = delta or 7
    return (today + dt.timedelta(days=delta)).isoformat()


@pytest.fixture(scope="session")
def sample_slot():
    return {"date": _next_friday_iso(), "window": "friday_evening"}


@pytest.fixture(scope="session")
def sample_address():
    return {
        "name": "Test Buyer",
        "email": "test.buyer@example.com",
        "line1": "123 Test Street",
        "line2": "Unit 4",
        "city": "Mississauga",
        "province": "ON",
        "postal_code": "L5B 1M2",
        "lat": 43.5890,
        "lng": -79.6441,
        "instructions": "Leave at door",
    }


def _find_menu_item_id(payload):
    """Recursively locate the first object that looks like a purchasable menu item."""
    if isinstance(payload, dict):
        if payload.get("item_id") and ("price_cents" in payload or "price" in payload):
            return payload["item_id"]
        for v in payload.values():
            found = _find_menu_item_id(v)
            if found:
                return found
    elif isinstance(payload, list):
        for v in payload:
            found = _find_menu_item_id(v)
            if found:
                return found
    return None


@pytest.fixture(scope="session")
def purchasable_item_id(client):
    """Return a menu item_id usable in a quote, or None if the menu is empty."""
    for path in ("/menu/anytime", "/menu/current"):
        r = client.get(path)
        if r.status_code == 200:
            found = _find_menu_item_id(r.json())
            if found:
                return found
    return None
