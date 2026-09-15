"""
Iteration 18 — Expo SDK 54 → 57 upgrade regression.
Scope: verify only backend endpoints that customer + admin flows depend on so we
can distinguish a JS/SDK-side regression from a server-side one. This is *not*
a full backend re-audit — deeper coverage lives in previous iteration files.
"""
import os
import requests
import pytest

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = os.environ["ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def guest_token(api):
    """Guest auth is the primary customer entry (Google is the other)."""
    r = api.post(f"{BASE_URL}/api/auth/guest", timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("session_token"), j
    return j["session_token"]


@pytest.fixture(scope="module")
def admin_token(api):
    r = api.post(
        f"{BASE_URL}/api/admin/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("access_token"), j
    return j["access_token"]


# ---------- Public menu (home / menu tabs) ----------

def test_menu_current_shape(api):
    r = api.get(f"{BASE_URL}/api/menu/current", timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "week_start" in j and "items" in j
    assert isinstance(j["items"], list)
    if j["items"]:
        it = j["items"][0]
        for k in ("item_id", "line_id", "name"):
            assert k in it, f"missing {k} in menu item: {it.keys()}"


# ---------- Quote (cart) ----------

_TORONTO = {
    "line1": "290 Bremner Blvd",
    "city": "Toronto",
    "province": "ON",
    "postal_code": "M5V 3L9",
}
_MILTON = {
    "line1": "6941 Derry Rd W",
    "city": "Milton",
    "province": "ON",
    "postal_code": "L9T 7H2",
}
_SLOT = {"date": "2026-01-16", "window": "friday_evening"}


def test_orders_quote_toronto_paid_tier(api, guest_token):
    r = api.post(
        f"{BASE_URL}/api/orders/quote",
        headers={"Authorization": f"Bearer {guest_token}"},
        json={"items": [], "address": _TORONTO, "slot": _SLOT},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert isinstance(j.get("delivery_fee_cents"), int)
    # Toronto ~54km from Milton → non-zero fee expected per policy
    assert j["delivery_fee_cents"] > 0, j
    # SDK-upgrade shouldn't change response shape used by cart UI
    for k in (
        "subtotal_cents",
        "delivery_fee_cents",
        "delivery_fee_tier",
        "delivery_time_window",
        "tax_cents",
        "total_cents",
    ):
        assert k in j, f"missing {k}: {list(j.keys())}"


def test_orders_quote_milton_free_tier(api, guest_token):
    r = api.post(
        f"{BASE_URL}/api/orders/quote",
        headers={"Authorization": f"Bearer {guest_token}"},
        json={"items": [], "address": _MILTON, "slot": _SLOT},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("delivery_fee_cents") == 0, j


# ---------- Admin login (admin portal) ----------

def test_admin_login(admin_token):
    assert admin_token  # verified by fixture


def test_admin_menu_reachable(api, admin_token):
    """Sanity: an authenticated admin GET works — proves token + auth
    middleware unaffected by SDK upgrade (frontend-only iteration)."""
    r = api.get(
        f"{BASE_URL}/api/admin/orders",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
