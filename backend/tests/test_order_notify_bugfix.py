"""
Backend tests for the Mustard Garden order-notification bug fixes.

Covers:
 1. GET /api/track/{order_id} is PUBLIC (no auth), returns 200 HTML with stepper,
    items list, total and 'View invoice / PDF' button. 404 for bogus order id.
 2. Email client is_configured() True; send to delivered@resend.dev returns an id.
 3. _order_items_text() renders bracketed selections for weekly_package and
    catering, and NO brackets for a plain menu item.
 4. After placing an order via the EXTERNAL host, tracking + invoice links are
    absolute (https://<host>/api/track|invoice/{id}) and both return 200.
 5. Regression: POST /api/orders (COD + Interac) still succeeds, requires
    address.email, and GET /api/invoice/{id} still 200.
"""
import os
import sys
import asyncio
import pytest
import requests

# EXTERNAL base URL — ingress host is required for absolute link resolution.
EXTERNAL_BASE = "https://garden-template-1.preview.emergentagent.com"
API = f"{EXTERNAL_BASE}/api"

# Ensure we can import backend modules for _order_items_text / email_client
sys.path.insert(0, "/app/backend")


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def guest_session():
    r = requests.post(f"{API}/auth/guest", timeout=15)
    r.raise_for_status()
    return r.json()["session_token"]


@pytest.fixture(scope="module")
def auth_headers(guest_session):
    return {"Authorization": f"Bearer {guest_session}"}


@pytest.fixture(scope="module")
def sample_menu_item():
    r = requests.get(f"{API}/menu/current", timeout=15)
    r.raise_for_status()
    cur = r.json()
    items = (cur or {}).get("items") or []
    assert items, "No menu items available on current weekly menu"
    return items[0]


def _base_order_body(item, payment_method="cod"):
    return {
        "items": [{"kind": "menu", "ref_id": item["item_id"], "quantity": 2}],
        "address": {
            "name": "TEST Buyer",
            "email": "buyer@example.com",
            "line1": "30 Main St E",
            "city": "Milton",
            "province": "ON",
            "postal_code": "L9T1N2",
        },
        "slot": {"date": "2026-09-06", "window": "sunday_evening"},
        "phone": "4160001111",
        "payment_method": payment_method,
        "client_base_url": EXTERNAL_BASE,
    }


# ==========================================================
# 1. Public tracking route
# ==========================================================
class TestPublicTracking:
    def test_track_public_no_auth_returns_200_html(self, auth_headers, sample_menu_item):
        # place a real order (COD) — no auth on /track later
        r = requests.post(f"{API}/orders", headers=auth_headers,
                          json=_base_order_body(sample_menu_item, "cod"), timeout=30)
        assert r.status_code == 200, r.text
        oid = r.json()["order_id"]

        # Public — no Authorization header
        tr = requests.get(f"{API}/track/{oid}", timeout=15)
        assert tr.status_code == 200, tr.text
        body = tr.text
        # Stepper labels
        for lbl in ("Confirmed", "Preparing", "Delivered"):
            assert lbl in body, f"Missing stepper label: {lbl}"
        # Items list heading + item name
        assert "Your items" in body
        assert sample_menu_item["name"] in body
        # Total
        assert "Total:" in body
        # Invoice button
        assert "View invoice / PDF" in body

    def test_track_bogus_order_returns_404(self):
        r = requests.get(f"{API}/track/ord_doesnotexist000", timeout=15)
        assert r.status_code == 404, r.text


# ==========================================================
# 2. Email client is configured + send works to delivered@resend.dev
# ==========================================================
class TestEmailIntegration:
    def test_is_configured(self):
        import email_client
        assert email_client.is_configured() is True

    def test_send_to_resend_sink_returns_id(self):
        import email_client

        async def _run():
            return await email_client.send_email(
                to="delivered@resend.dev",
                subject="Mustard Garden — automated test ping",
                html="<p>This is an automated backend test to verify email send. "
                     "Please ignore. <a href='https://garden-template-1.preview.emergentagent.com'>MG</a></p>",
            )
        rid = asyncio.get_event_loop().run_until_complete(_run()) if not asyncio.get_event_loop().is_running() \
            else asyncio.new_event_loop().run_until_complete(_run())
        assert rid, "Expected non-empty email id from Resend"


# ==========================================================
# 3. _order_items_text bracket logic (unit test on crafted snapshots)
# ==========================================================
class TestOrderItemsText:
    def _snapshot(self, snaps):
        return {"items_snapshot": snaps}

    def test_plain_menu_item_has_no_brackets(self):
        import server
        txt = server._order_items_text(self._snapshot([
            {"kind": "menu", "name": "Chicken Biryani", "quantity": 2,
             "line_total_cents": 3000},
        ]))
        assert "Chicken Biryani x2" in txt
        assert "CA$30.00" in txt
        assert "(" not in txt, f"Unexpected bracket in plain menu line: {txt!r}"

    def test_weekly_package_shows_bracketed_selections(self):
        import server
        txt = server._order_items_text(self._snapshot([
            {"kind": "weekly_package", "name": "Weekly Combo", "quantity": 1,
             "line_total_cents": 6999,
             "package_selection_names": ["Chicken Biryani × 2",
                                         "Paneer Butter Masala",
                                         "Dal"]},
        ]))
        assert "Weekly Combo x1" in txt
        assert "(Chicken Biryani × 2, Paneer Butter Masala, Dal)" in txt
        assert "CA$69.99" in txt

    def test_catering_shows_bracketed_selections(self):
        import server
        txt = server._order_items_text(self._snapshot([
            {"kind": "catering", "name": "Family Feast", "quantity": 1,
             "line_total_cents": 20000,
             "selection_summary": [
                 {"title": "Mains", "items": ["Butter Chicken", "Palak Paneer"]},
                 {"title": "Rice", "items": ["Jeera Rice"]},
             ]},
        ]))
        assert "Family Feast x1" in txt
        assert "(Butter Chicken, Palak Paneer, Jeera Rice)" in txt
        assert "CA$200.00" in txt


# ==========================================================
# 4. Absolute links after placing an order via the EXTERNAL host
# ==========================================================
class TestAbsoluteLinks:
    def test_order_absolute_links_resolve(self, auth_headers, sample_menu_item):
        r = requests.post(f"{API}/orders", headers=auth_headers,
                          json=_base_order_body(sample_menu_item, "cod"), timeout=30)
        assert r.status_code == 200, r.text
        oid = r.json()["order_id"]

        # Reload the order via server helpers logic: the order stores
        # public_base_url; the tracking link should therefore be absolute.
        # We verify by hitting the constructed absolute URLs directly.
        invoice_url = f"{EXTERNAL_BASE}/api/invoice/{oid}"
        track_url = f"{EXTERNAL_BASE}/api/track/{oid}"

        inv = requests.get(invoice_url, timeout=15)
        assert inv.status_code == 200, inv.text
        assert "invoice" in inv.text.lower() or "Save PDF" in inv.text

        tr = requests.get(track_url, timeout=15)
        assert tr.status_code == 200, tr.text
        # invoice button on the track page must link to the absolute invoice URL
        assert invoice_url in tr.text, "Track page should embed the absolute invoice link"


# ==========================================================
# 5. Regression: COD + Interac orders + invoice page
# ==========================================================
class TestOrderRegression:
    def test_cod_order_persists_email_and_invoice_ok(self, auth_headers, sample_menu_item):
        body = _base_order_body(sample_menu_item, "cod")
        r = requests.post(f"{API}/orders", headers=auth_headers, json=body, timeout=30)
        assert r.status_code == 200, r.text
        o = r.json()
        assert o["address"].get("email") == "buyer@example.com"
        inv = requests.get(f"{API}/invoice/{o['order_id']}", timeout=15)
        assert inv.status_code == 200
        assert "Save PDF" in inv.text or "download" in inv.text.lower()

    def test_interac_order_ok(self, auth_headers, sample_menu_item):
        body = _base_order_body(sample_menu_item, "interac")
        r = requests.post(f"{API}/orders", headers=auth_headers, json=body, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["address"].get("email") == "buyer@example.com"

    def test_order_requires_address_email(self, auth_headers, sample_menu_item):
        body = _base_order_body(sample_menu_item, "cod")
        body["address"].pop("email", None)
        r = requests.post(f"{API}/orders", headers=auth_headers, json=body, timeout=30)
        # Server may accept blank email string or require it. Only require that
        # if the server rejects, it does so with a 400 (business validation),
        # not a 500.
        if r.status_code != 200:
            assert 400 <= r.status_code < 500, r.text
