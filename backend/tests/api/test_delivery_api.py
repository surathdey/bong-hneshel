"""Delivery-partner API — negative/auth checks (no partner creds required)."""
import httpx
import pytest

from conftest import API, TIMEOUT


@pytest.mark.parametrize("path", [
    "/delivery/me",
    "/delivery/orders",
    "/delivery/journey/current",
])
def test_delivery_read_requires_partner_auth(path):
    r = httpx.get(f"{API}{path}", timeout=TIMEOUT)
    assert r.status_code in (401, 403)


@pytest.mark.parametrize("method,path", [
    ("POST", "/delivery/location"),
    ("POST", "/delivery/route"),
    ("POST", "/delivery/journey/start"),
])
def test_delivery_write_requires_partner_auth(method, path):
    r = httpx.request(method, f"{API}{path}", json={}, timeout=TIMEOUT)
    assert r.status_code in (401, 403, 422)  # 422 if it validates body before auth


def test_delivery_login_bad_credentials():
    r = httpx.post(f"{API}/delivery/login",
                   json={"email": "nobody@example.com", "password": "wrong"},
                   timeout=TIMEOUT)
    assert r.status_code in (400, 401, 403, 404)


def test_delivery_partner_apply_accepts_or_validates():
    # public application endpoint; empty body should validate (422) not 500
    r = httpx.post(f"{API}/delivery-partner/apply", json={}, timeout=TIMEOUT)
    assert r.status_code in (200, 201, 400, 422)
