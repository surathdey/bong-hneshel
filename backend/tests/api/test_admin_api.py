"""Admin API: auth, read endpoints, and a safe coupon CRUD round-trip."""
import uuid

import httpx
import pytest

from conftest import API, TIMEOUT

ADMIN_GET_ENDPOINTS = [
    "/admin/me",
    "/admin/stats",
    "/admin/settings",
    "/admin/orders",
    "/admin/customers",
    "/admin/master-menu",
    "/admin/menus",
    "/admin/catering",
    "/admin/coupons",
    "/admin/delivery-partners",
    "/admin/integrations",
    "/admin/billing/summary",
    "/admin/order-builder",
    "/admin/always-available",
]


def test_admin_login(admin_token):
    assert isinstance(admin_token, str) and len(admin_token) > 20


@pytest.mark.parametrize("path", ADMIN_GET_ENDPOINTS)
def test_admin_get_endpoints(admin_headers, path):
    r = httpx.get(f"{API}{path}", headers=admin_headers, timeout=TIMEOUT)
    assert r.status_code == 200, f"GET {path} -> {r.status_code}: {r.text[:300]}"
    r.json()


@pytest.mark.parametrize("path", ["/admin/orders", "/admin/settings", "/admin/coupons"])
def test_admin_endpoints_reject_no_token(path):
    r = httpx.get(f"{API}{path}", timeout=TIMEOUT)
    assert r.status_code in (401, 403)


def test_admin_endpoints_reject_bad_token():
    r = httpx.get(f"{API}/admin/orders", headers={"Authorization": "Bearer garbage"}, timeout=TIMEOUT)
    assert r.status_code in (401, 403)


def test_admin_coupon_crud_roundtrip(admin_headers):
    code = f"PYTEST{uuid.uuid4().hex[:6].upper()}"
    create = {
        "code": code,
        "discount_type": "percent",
        "value": 15,
        "active": True,
        "min_order_cents": 1000,
        "description": "pytest temporary coupon",
        "first_time_only": False,
    }
    # CREATE
    r = httpx.post(f"{API}/admin/coupons", json=create, headers=admin_headers, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    # READ (list must contain it)
    lst = httpx.get(f"{API}/admin/coupons", headers=admin_headers, timeout=TIMEOUT).json()
    codes = [c["code"] for c in lst.get("coupons", [])]
    assert code in codes
    # UPDATE -> fixed $5
    upd = dict(create, discount_type="fixed", value=500, description="updated")
    r = httpx.put(f"{API}/admin/coupons/{code}", json=upd, headers=admin_headers, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    # DELETE (cleanup)
    r = httpx.request("DELETE", f"{API}/admin/coupons/{code}", headers=admin_headers, timeout=TIMEOUT)
    assert r.status_code in (200, 204)


def test_admin_coupon_validation_rejects_bad_percent(admin_headers):
    bad = {
        "code": f"PYBAD{uuid.uuid4().hex[:5].upper()}",
        "discount_type": "percent",
        "value": 500,  # invalid: >100
        "active": True,
        "min_order_cents": 0,
        "description": "",
        "first_time_only": False,
    }
    r = httpx.post(f"{API}/admin/coupons", json=bad, headers=admin_headers, timeout=TIMEOUT)
    assert r.status_code == 400
