"""Customer flow: guest auth, profile, saved address, quote, orders."""
import httpx
import pytest

from conftest import API, TIMEOUT


def test_guest_auth_returns_token(guest_session):
    assert guest_session.get("session_token")
    assert guest_session.get("user")


def test_auth_me(guest_headers):
    r = httpx.get(f"{API}/auth/me", headers=guest_headers, timeout=TIMEOUT)
    assert r.status_code == 200
    assert r.json().get("user") or r.json().get("email") or r.json().get("user_id")


def test_auth_me_requires_token():
    r = httpx.get(f"{API}/auth/me", timeout=TIMEOUT)
    assert r.status_code in (401, 403)


def test_orders_list_for_new_guest(guest_headers):
    r = httpx.get(f"{API}/orders", headers=guest_headers, timeout=TIMEOUT)
    assert r.status_code == 200
    body = r.json()
    orders = body if isinstance(body, list) else body.get("orders", [])
    assert isinstance(orders, list)


def test_saved_address_create_then_delete(guest_headers):
    payload = {
        "line1": "50 Test Ave",
        "line2": "",
        "city": "Toronto",
        "province": "ON",
        "postal_code": "M5V 2T6",
    }
    r = httpx.post(f"{API}/me/address", json=payload, headers=guest_headers, timeout=TIMEOUT)
    assert r.status_code in (200, 201), r.text
    d = httpx.request("DELETE", f"{API}/me/address", headers=guest_headers, timeout=TIMEOUT)
    assert d.status_code in (200, 204)


def test_first_time_coupon_endpoint(guest_headers):
    # Logged-in (guest) users can query first-time eligibility; must not 500.
    r = httpx.get(f"{API}/coupons/first-time", headers=guest_headers, timeout=TIMEOUT)
    assert r.status_code in (200, 404)


def test_quote_with_menu_item(guest_headers, purchasable_item_id, sample_address, sample_slot):
    if not purchasable_item_id:
        pytest.skip("no purchasable menu item available (menu empty)")
    payload = {
        "items": [{"kind": "menu", "ref_id": purchasable_item_id, "quantity": 1}],
        "address": sample_address,
        "slot": sample_slot,
        "phone": "+14165550123",
        "payment_method": "cod",
    }
    r = httpx.post(f"{API}/orders/quote", json=payload, headers=guest_headers, timeout=TIMEOUT)
    # 200 when the ordering window is open; 400 when closed / item unavailable.
    assert r.status_code in (200, 400), r.text
    if r.status_code == 200:
        body = r.json()
        assert "total_cents" in body or "total" in body or "subtotal_cents" in body
