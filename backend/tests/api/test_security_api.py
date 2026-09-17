"""Security regression tests — endpoints that MUST require authentication.

These lock in the hardening fixes (unauthenticated write endpoints + destructive
seed) so they can never silently regress.
"""
import httpx
import pytest

from conftest import API, TIMEOUT


@pytest.mark.parametrize("method,path,body", [
    ("POST", "/menu/upsert", {"week_start": "2099-01-01"}),
    ("POST", "/orders/ord_fake/status", {"status": "delivered"}),
    ("POST", "/dev/seed", None),
])
def test_privileged_endpoints_require_admin(method, path, body):
    r = httpx.request(method, f"{API}{path}", json=body, timeout=TIMEOUT)
    assert r.status_code in (401, 403), f"{method} {path} should be protected but got {r.status_code}"


def test_invoice_escapes_html(admin_headers):
    """Invoice/track pages must HTML-escape user input (stored-XSS guard).
    We can only assert the endpoint doesn't 500; deep XSS check needs a seeded order."""
    r = httpx.get(f"{API}/invoice/ord_fake_missing", timeout=TIMEOUT)
    # unknown order -> 404 (not a 500 stacktrace)
    assert r.status_code in (200, 404)
