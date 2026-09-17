"""Public / unauthenticated API endpoints (read-only)."""
import pytest

# (path, expected status codes considered a pass)
PUBLIC_GET_ENDPOINTS = [
    "/",
    "/settings",
    "/brand",
    "/platform/status",
    "/menu/current",
    "/menu/anytime",
    "/menu/upcoming",
    "/menu/history",
    "/catering",
    "/legal/privacy",
    "/health/web-bundle",
]


@pytest.mark.parametrize("path", PUBLIC_GET_ENDPOINTS)
def test_public_get_returns_200(client, path):
    r = client.get(path)
    assert r.status_code == 200, f"GET {path} -> {r.status_code}: {r.text[:300]}"
    # Some endpoints return HTML (root '/' and the legal page); only parse JSON responses.
    if "application/json" in r.headers.get("content-type", ""):
        r.json()


def test_settings_shape(client):
    data = client.get("/settings").json()
    assert isinstance(data, dict)
    # business settings should never leak secret payment keys to the public
    dumped = str(data).lower()
    assert "sk_live" not in dumped and "sk_test" not in dumped, "Stripe secret key leaked in /settings!"


def test_coupon_lookup_unknown_code(client):
    r = client.get("/coupons/DEFINITELY_NOT_A_CODE_123")
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        body = r.json()
        # an unknown code must not report itself as a valid/active coupon
        assert body.get("valid") in (False, None) or body.get("active") in (False, None)


def test_places_autocomplete_requires_query(client):
    # missing required 'q' should be a client error, not a 500
    r = client.get("/places/autocomplete")
    assert r.status_code in (400, 422)
