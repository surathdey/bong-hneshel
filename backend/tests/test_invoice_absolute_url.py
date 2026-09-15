"""
Iteration 20 — verify that the invoice link stamped on an order is an ABSOLUTE
public URL (https://<host>/api/invoice/{order_id}) built from the ingress
`x-forwarded-host` header (or client_base_url fallback), never a bare relative
path or a localhost origin.

Tests run against the EXTERNAL public base URL only, because the fix depends on
the reverse proxy setting `x-forwarded-host` / `host`.
"""
import os
import re
import pytest
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://garden-template-1.preview.emergentagent.com").rstrip("/")
PUBLIC_HOST = re.sub(r"^https?://", "", BASE)  # e.g. garden-template-1.preview.emergentagent.com


# --- shared fixtures ---
@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def guest_token(api):
    r = api.post(f"{BASE}/api/auth/guest")
    assert r.status_code == 200, r.text
    tok = r.json().get("session_token")
    assert tok, "no session_token"
    return tok


@pytest.fixture(scope="module")
def auth_headers(guest_token):
    return {"Authorization": f"Bearer {guest_token}"}


@pytest.fixture(scope="module")
def menu_item(api):
    r = api.get(f"{BASE}/api/menu/current")
    assert r.status_code == 200, r.text
    items = (r.json() or {}).get("items") or []
    assert items, "current menu is empty"
    return items[0]


def _order_body(menu_item, payment_method="cod", email="buyer_test20@example.com"):
    return {
        "items": [{"kind": "menu", "ref_id": menu_item["item_id"], "quantity": 1}],
        "address": {
            "name": "Test Buyer",
            "email": email,
            "line1": "30 Main St E",
            "city": "Milton",
            "province": "ON",
            "postal_code": "L9T1N2",
        },
        "slot": {"date": "2026-09-06", "window": "sunday_evening"},
        "phone": "4160001111",
        "payment_method": payment_method,
        "client_base_url": BASE,
    }


# --- regression: /menu/current ---
def test_menu_current_ok(api):
    r = api.get(f"{BASE}/api/menu/current")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body.get("items"), list)


# --- COD order: absolute public_base_url + absolute invoice URL served 200 ---
def test_cod_order_stamps_absolute_public_base_url(api, auth_headers, menu_item):
    body = _order_body(menu_item, payment_method="cod")
    r = api.post(f"{BASE}/api/orders", headers=auth_headers, json=body)
    assert r.status_code == 200, r.text
    o = r.json()
    order_id = o["order_id"]

    # email persisted on address
    assert o["address"].get("email") == body["address"]["email"]

    # public_base_url is stamped on the order document (verify via GET which reads DB)
    got = api.get(f"{BASE}/api/orders/{order_id}", headers=auth_headers)
    assert got.status_code == 200, got.text
    persisted = got.json()
    pub = persisted.get("public_base_url")
    assert pub, f"public_base_url missing from persisted order: {persisted}"
    assert pub.startswith("https://"), f"public_base_url not https: {pub}"
    assert "localhost" not in pub and "127.0.0.1" not in pub, f"public_base_url points to localhost: {pub}"
    # host must match the ingress host we hit
    assert PUBLIC_HOST in pub, f"public_base_url host mismatch: {pub} vs {PUBLIC_HOST}"

    # invoice link is fetchable and renders an invoice page containing a PDF button
    invoice_url = f"{pub}/api/invoice/{order_id}"
    inv = api.get(invoice_url)
    assert inv.status_code == 200, f"invoice fetch failed: {inv.status_code} {inv.text[:200]}"
    text_lower = inv.text.lower()
    assert ("save pdf" in text_lower) or ("print" in text_lower) or ("download" in text_lower), \
        "invoice page missing Print/Save PDF affordance"
    # invoice mentions the order id
    assert order_id in inv.text, "invoice page missing order_id"


# --- Interac order: same shape, invoice absolute + 200 ---
def test_interac_order_stamps_absolute_public_base_url(api, auth_headers, menu_item):
    body = _order_body(menu_item, payment_method="interac", email="buyer_test20_i@example.com")
    r = api.post(f"{BASE}/api/orders", headers=auth_headers, json=body)
    assert r.status_code == 200, r.text
    o = r.json()
    order_id = o["order_id"]

    got = api.get(f"{BASE}/api/orders/{order_id}", headers=auth_headers)
    assert got.status_code == 200, got.text
    pub = got.json().get("public_base_url")
    assert pub and pub.startswith("https://") and PUBLIC_HOST in pub, f"bad public_base_url: {pub}"

    invoice_url = f"{pub}/api/invoice/{order_id}"
    inv = api.get(invoice_url)
    assert inv.status_code == 200
    assert order_id in inv.text


# --- tracking link derivable for guests: <host>/order/<id> reachable (frontend route) ---
def test_track_link_is_absolute_and_uses_public_host(api, auth_headers, menu_item):
    body = _order_body(menu_item, payment_method="cod", email="buyer_test20_t@example.com")
    r = api.post(f"{BASE}/api/orders", headers=auth_headers, json=body)
    assert r.status_code == 200, r.text
    o = r.json()
    order_id = o["order_id"]

    got = api.get(f"{BASE}/api/orders/{order_id}", headers=auth_headers)
    assert got.status_code == 200
    pub = got.json().get("public_base_url")

    assert pub and pub.startswith("https://")
    track = f"{pub}/order/{order_id}"
    # Only require it starts with https and the public host — Expo web route may
    # return a bundle 200 or a 404 for the SSR-less shell; we just prove the URL
    # form is clickable/absolute.
    assert track.startswith(f"https://{PUBLIC_HOST}/order/"), track


# --- email required on address (regression) ---
def test_order_without_email_still_accepted_but_field_missing(api, auth_headers, menu_item):
    body = _order_body(menu_item)
    body["address"].pop("email", None)
    r = api.post(f"{BASE}/api/orders", headers=auth_headers, json=body)
    # We don't assert 4xx — we only assert either (a) the API rejects it OR
    # (b) it accepts and the persisted address has no email (then downstream
    # notification silently skips email). Both are acceptable per PRD; the
    # important thing is: WHEN email IS provided, it IS persisted (covered above).
    if r.status_code == 200:
        assert not r.json().get("address", {}).get("email"), \
            "server invented an email that was not provided"
    else:
        assert r.status_code in (400, 422)


# --- invoice endpoint returns HTML that references the invoice/order ---
def test_invoice_endpoint_returns_html(api, auth_headers, menu_item):
    body = _order_body(menu_item, payment_method="cod", email="buyer_test20_h@example.com")
    r = api.post(f"{BASE}/api/orders", headers=auth_headers, json=body)
    assert r.status_code == 200
    oid = r.json()["order_id"]

    inv = api.get(f"{BASE}/api/invoice/{oid}")
    assert inv.status_code == 200
    ctype = inv.headers.get("content-type", "").lower()
    assert "html" in ctype, f"invoice content-type not html: {ctype}"
    assert oid in inv.text
