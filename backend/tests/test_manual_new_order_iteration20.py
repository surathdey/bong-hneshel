"""Curry & Co. — Iteration 20 tests.

Backend contract verification for the Admin **New Order** modal flow.

Covers:
  1. POST /api/admin/login → returns access_token
  2. GET  /api/admin/order-builder → returns delivery_slots + master_menu + weeks
                                     + catering + delivery_partners + settings
  3. POST /api/admin/customers → creates a new customer inline (name+phone)
  4. POST /api/admin/orders/create → à la carte order for an EXISTING customer
  5. POST /api/admin/orders/create → catering order for a NEW inline customer
  6. driver_partner_id present → order.status auto-becomes 'packed'
  7. mark_as_paid=true → payment_status = 'paid';
     mark_as_paid=false → payment_status = 'cod_pending' (COD) etc.
  8. GET  /api/admin/orders → lists the newly created manual orders
  9. Validation: missing customer / items / slot / address → 4xx
 10. Totals: tax + delivery_fee + subtotal reconcile against settings

Runs against the deployed preview backend (EXPO_PUBLIC_BACKEND_URL).
"""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import pytest
import requests


# ---------------------------------------------------------------- setup ---
def _load_frontend_env() -> None:
    env = Path("/app/frontend/.env")
    if env.exists():
        for line in env.read_text().splitlines():
            m = re.match(r'^\s*([A-Z0-9_]+)\s*=\s*"?([^"\s]+)"?\s*$', line)
            if m:
                os.environ.setdefault(m.group(1), m.group(2))


_load_frontend_env()
BASE_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@curryandco.local"
ADMIN_PASSWORD = "curry@admin2026"


def _uniq_email(tag: str = "cust") -> str:
    """Every new customer needs a UNIQUE email because the current backend
    schema has a non-sparse unique index on users.email — inserting two docs
    with email=None (the common case for phone-only customers) triggers an
    E11000 duplicate-key error. See TestNullEmailRegression."""
    return f"TEST_{tag}_{uuid.uuid4().hex[:8]}@example.com"


# ---------------------------------------------------------------- fixtures ---
@pytest.fixture(scope="session")
def api_client() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session", autouse=True)
def _seed(api_client: requests.Session) -> None:
    # Ensure master_menu, catering, coupons exist (orders may have been purged)
    r = api_client.post(f"{API}/dev/seed")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert body.get("master_items", 0) > 0
    assert body.get("packages", 0) > 0


@pytest.fixture(scope="session")
def admin_token(api_client: requests.Session) -> str:
    r = api_client.post(
        f"{API}/admin/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    assert token
    return token


@pytest.fixture(scope="session")
def admin_headers(admin_token: str) -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_token}",
    }


@pytest.fixture(scope="session")
def order_builder(api_client: requests.Session, admin_headers: dict) -> dict:
    r = api_client.get(f"{API}/admin/order-builder", headers=admin_headers)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="session")
def sample_address() -> dict:
    return {
        "line1": "123 TEST Bloor St W",
        "line2": "Suite 4",
        "city": "Toronto",
        "province": "ON",
        "postal_code": "M5S 1A1",
        "instructions": "TEST — ring bell twice",
    }


@pytest.fixture(scope="session")
def sample_slot(order_builder: dict) -> dict:
    slots = order_builder.get("delivery_slots") or []
    assert slots, "order-builder returned no delivery_slots"
    # Trim to what DeliverySlot expects
    return {"date": slots[0]["date"], "window": slots[0]["window"]}


@pytest.fixture(scope="session")
def menu_item(order_builder: dict) -> dict:
    """Pick a real menu item to order.  Prefer weekly-menu items so the price
    resolution path exercises the embedded weekly_menu branch."""
    weeks = order_builder.get("weeks") or []
    for wk in weeks:
        for it in (wk.get("items") or []):
            if it.get("item_id") and it.get("price_cents"):
                return {
                    "item_id": it["item_id"],
                    "price_cents": it["price_cents"],
                    "name": it.get("name"),
                }
    # Fallback to master menu
    for m in order_builder.get("master_menu") or []:
        if m.get("item_id") and m.get("default_price_cents"):
            return {
                "item_id": m["item_id"],
                "price_cents": m["default_price_cents"],
                "name": m.get("name"),
            }
    pytest.fail("No menu items available to seed test order")


# ---------------------------------------------------------------- tests ---

# 1) Admin login
class TestAdminLogin:
    def test_login_returns_access_token(self, api_client: requests.Session):
        r = api_client.post(
            f"{API}/admin/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "access_token" in body and body["access_token"]
        assert body.get("token_type") == "bearer"
        assert body.get("admin", {}).get("email") == ADMIN_EMAIL

    def test_login_bad_password_401(self, api_client: requests.Session):
        r = api_client.post(
            f"{API}/admin/login",
            json={"email": ADMIN_EMAIL, "password": "WRONG_PASS_2026"},
        )
        assert r.status_code in (400, 401, 403), r.text


# 2) Order builder bundle
class TestOrderBuilder:
    def test_bundle_shape(self, order_builder: dict):
        for key in (
            "delivery_slots", "master_menu", "weeks",
            "catering", "delivery_partners", "settings",
        ):
            assert key in order_builder, f"missing key: {key}"

        # delivery_slots — list of {date, window, label}, in the future
        slots = order_builder["delivery_slots"]
        assert isinstance(slots, list) and len(slots) > 0
        for s in slots[:3]:
            assert set(s.keys()) >= {"date", "window", "label"}
            assert re.match(r"\d{4}-\d{2}-\d{2}", s["date"])

        # master_menu has priced items
        mm = order_builder["master_menu"]
        assert isinstance(mm, list) and len(mm) > 0
        assert any(m.get("default_price_cents") for m in mm)

        # settings block has the fields the modal needs
        st = order_builder["settings"]
        for k in ("delivery_fee_cents", "tax_rate_bps", "tax_label",
                  "tax_enabled", "currency", "payment_methods"):
            assert k in st, f"settings missing {k}"

    def test_requires_admin_auth(self, api_client: requests.Session):
        r = api_client.get(f"{API}/admin/order-builder")
        assert r.status_code in (401, 403), r.text


# 3) Inline customer creation
class TestAdminCustomerInline:
    def test_create_inline_customer(self, api_client: requests.Session,
                                    admin_headers: dict):
        phone = f"+1 416-555-{uuid.uuid4().int % 9000 + 1000:04d}"
        r = api_client.post(
            f"{API}/admin/customers",
            headers=admin_headers,
            json={"name": "TEST Ananya Basu",
                  "phone": phone,
                  "email": f"TEST_{uuid.uuid4().hex[:6]}@example.com"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["existed"] is False
        assert body["user_id"].startswith("user_")
        assert body["user"]["phone"] == phone
        assert body["user"]["name"] == "TEST Ananya Basu"
        # No _id leak
        assert "_id" not in body["user"]

    def test_missing_name_or_phone_returns_4xx(self, api_client: requests.Session,
                                               admin_headers: dict):
        r = api_client.post(
            f"{API}/admin/customers",
            headers=admin_headers,
            json={"name": "", "phone": ""},
        )
        # 400 from our check OR 422 from Pydantic (both are 4xx)
        assert 400 <= r.status_code < 500, r.text

    def test_dedupe_on_phone(self, api_client: requests.Session,
                             admin_headers: dict):
        phone = f"+1 416-555-{uuid.uuid4().int % 9000 + 1000:04d}"
        r1 = api_client.post(
            f"{API}/admin/customers",
            headers=admin_headers,
            json={"name": "TEST Deduper", "phone": phone,
                  "email": _uniq_email("dedupe")},
        )
        assert r1.status_code == 200
        uid1 = r1.json()["user_id"]
        r2 = api_client.post(
            f"{API}/admin/customers",
            headers=admin_headers,
            json={"name": "TEST Deduper 2", "phone": phone,
                  "email": _uniq_email("dedupe2")},
        )
        assert r2.status_code == 200
        assert r2.json()["existed"] is True
        assert r2.json()["user_id"] == uid1


# 4) Manual order for EXISTING customer with an à la carte item + totals check
class TestManualOrderExistingCustomer:
    def test_existing_customer_alacarte(
        self, api_client: requests.Session, admin_headers: dict,
        order_builder: dict, sample_address: dict, sample_slot: dict,
        menu_item: dict,
    ):
        # First create a customer we can then pass by user_id
        phone = f"+1 647-555-{uuid.uuid4().int % 9000 + 1000:04d}"
        cr = api_client.post(
            f"{API}/admin/customers",
            headers=admin_headers,
            json={"name": "TEST Existing", "phone": phone,
                  "email": _uniq_email("existing")},
        )
        assert cr.status_code == 200
        uid = cr.json()["user_id"]

        payload = {
            "user_id": uid,
            "items": [{"kind": "menu", "ref_id": menu_item["item_id"],
                       "quantity": 2}],
            "address": sample_address,
            "slot": sample_slot,
            "phone": phone,
            "payment_method": "cod",
            "mark_as_paid": False,
        }
        r = api_client.post(f"{API}/admin/orders/create",
                            headers=admin_headers, json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        order = body["order"]
        assert order["user_id"] == uid
        assert order["created_by_admin"] is True
        assert order["payment_method"] == "cod"
        assert order["payment_status"] == "cod_pending"
        assert order["status"] == "confirmed"  # admin non-paid → 'confirmed'
        assert order["items_snapshot"][0]["ref_id"] == menu_item["item_id"]
        assert order["items_snapshot"][0]["quantity"] == 2

        # Verify totals math: subtotal + delivery_fee + tax = total
        st = order_builder["settings"]
        delivery_fee = st["delivery_fee_cents"]
        subtotal = menu_item["price_cents"] * 2
        assert order["subtotal_cents"] == subtotal
        assert order["delivery_fee_cents"] == delivery_fee
        # Tax may be disabled for COD; either way must reconcile.
        assert order["tax_cents"] >= 0
        assert order["total_cents"] == subtotal + delivery_fee + order["tax_cents"]

        # Save order_id for later regression tests
        pytest._existing_order_id = order["order_id"]  # type: ignore[attr-defined]

    def test_existing_order_appears_in_admin_list(
        self, api_client: requests.Session, admin_headers: dict,
    ):
        order_id = getattr(pytest, "_existing_order_id", None)
        assert order_id, "previous test did not persist order_id"
        r = api_client.get(f"{API}/admin/orders", headers=admin_headers)
        assert r.status_code == 200, r.text
        orders = r.json()
        assert isinstance(orders, list)
        ids = {o["order_id"] for o in orders}
        assert order_id in ids


# 5) Manual order for NEW inline customer + catering package
class TestManualOrderNewInlineCatering:
    def test_new_customer_with_catering(
        self, api_client: requests.Session, admin_headers: dict,
        order_builder: dict, sample_address: dict, sample_slot: dict,
    ):
        # Pick a catering package that is not a "quote-only" one
        pkgs = [p for p in (order_builder.get("catering") or [])
                if not p.get("is_custom_quote")]
        assert pkgs, "No bookable catering packages seeded"
        pkg = pkgs[0]

        # Build valid group_selections satisfying min/max per default tier
        default_tier = next(
            (t for t in (pkg.get("upgrade_tiers") or []) if t.get("is_default")),
            (pkg.get("upgrade_tiers") or [None])[0],
        )
        group_overrides = (default_tier or {}).get("group_overrides", {}) or {}
        group_selections: dict = {}
        for g in (pkg.get("choice_groups") or []):
            gid = g["group_id"]
            ov = group_overrides.get(gid) or {}
            min_sel = ov.get("min_select", g.get("min_select", 1))
            opts = g.get("option_master_ids", [])
            assert len(opts) >= min_sel, f"Group {gid} lacks options for min_sel"
            group_selections[gid] = opts[:min_sel]

        catering_item = {
            "kind": "catering",
            "ref_id": pkg["package_id"],
            "quantity": 1,
            "catering_guest_count": max(pkg.get("min_guests", 10), 10),
            "catering_selections": {
                "tier_id": (default_tier or {}).get("tier_id"),
                "group_selections": group_selections,
                "premium_selections": [],
            },
        }

        new_phone = f"+1 437-555-{uuid.uuid4().int % 9000 + 1000:04d}"
        new_email = f"TEST_new_{uuid.uuid4().hex[:6]}@example.com"
        payload = {
            "new_customer": {
                "name": "TEST Inline Newby",
                "phone": new_phone,
                "email": new_email,
                "address": sample_address,
            },
            "items": [catering_item],
            "address": sample_address,
            "slot": sample_slot,
            "phone": new_phone,
            "payment_method": "interac",
            "mark_as_paid": True,
        }
        r = api_client.post(f"{API}/admin/orders/create",
                            headers=admin_headers, json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        order = body["order"]
        customer = body["customer"]
        assert customer["user_id"].startswith("user_")
        assert customer["phone"] == new_phone
        # payment
        assert order["payment_method"] == "interac"
        assert order["payment_status"] == "paid"
        assert order["status"] == "confirmed"
        # catering snapshot preserved
        snap = order["items_snapshot"][0]
        assert snap["kind"] == "catering"
        assert snap["ref_id"] == pkg["package_id"]

        pytest._new_customer_id = customer["user_id"]  # type: ignore[attr-defined]
        pytest._catering_order_id = order["order_id"]  # type: ignore[attr-defined]


# 6) driver_partner_id → status becomes 'packed'
class TestDriverAutoAssign:
    def test_driver_assignment_marks_packed(
        self, api_client: requests.Session, admin_headers: dict,
        order_builder: dict, sample_address: dict, sample_slot: dict,
        menu_item: dict,
    ):
        partners = order_builder.get("delivery_partners") or []
        if not partners:
            pytest.skip("No active delivery partners seeded")
        driver = partners[0]

        phone = f"+1 905-555-{uuid.uuid4().int % 9000 + 1000:04d}"
        payload = {
            "new_customer": {
                "name": "TEST Driver Assign",
                "phone": phone,
                "email": _uniq_email("driver"),
            },
            "items": [{"kind": "menu", "ref_id": menu_item["item_id"],
                       "quantity": 1}],
            "address": sample_address,
            "slot": sample_slot,
            "phone": phone,
            "payment_method": "cod",
            "mark_as_paid": False,
            "driver_partner_id": driver["partner_id"],
        }
        r = api_client.post(f"{API}/admin/orders/create",
                            headers=admin_headers, json=payload)
        assert r.status_code == 200, r.text
        order = r.json()["order"]
        assert order["status"] == "packed"
        assert order["delivery_partner_id"] == driver["partner_id"]
        assert order["delivery_status"] == "assigned"

    def test_bad_driver_id_returns_4xx(
        self, api_client: requests.Session, admin_headers: dict,
        sample_address: dict, sample_slot: dict, menu_item: dict,
    ):
        phone = f"+1 905-555-{uuid.uuid4().int % 9000 + 1000:04d}"
        payload = {
            "new_customer": {"name": "TEST BadDriver", "phone": phone,
                             "email": _uniq_email("baddrv")},
            "items": [{"kind": "menu", "ref_id": menu_item["item_id"], "quantity": 1}],
            "address": sample_address,
            "slot": sample_slot,
            "phone": phone,
            "payment_method": "cod",
            "driver_partner_id": "partner_does_not_exist_xyz",
        }
        r = api_client.post(f"{API}/admin/orders/create",
                            headers=admin_headers, json=payload)
        assert 400 <= r.status_code < 500, r.text


# 7) mark_as_paid toggles payment_status
class TestMarkAsPaidBehavior:
    @pytest.mark.parametrize("mark,method,expected", [
        (True,  "cod",     "paid"),
        (True,  "interac", "paid"),
        (True,  "card",    "paid"),
        (False, "cod",     "cod_pending"),
        (False, "interac", "interac_pending"),
        (False, "card",    "pending"),
    ])
    def test_payment_status(
        self, api_client: requests.Session, admin_headers: dict,
        sample_address: dict, sample_slot: dict, menu_item: dict,
        mark: bool, method: str, expected: str,
    ):
        phone = f"+1 226-555-{uuid.uuid4().int % 9000 + 1000:04d}"
        payload = {
            "new_customer": {"name": f"TEST PayStatus {method}", "phone": phone,
                             "email": _uniq_email(f"pay-{method}-{mark}")},
            "items": [{"kind": "menu", "ref_id": menu_item["item_id"], "quantity": 1}],
            "address": sample_address,
            "slot": sample_slot,
            "phone": phone,
            "payment_method": method,
            "mark_as_paid": mark,
        }
        r = api_client.post(f"{API}/admin/orders/create",
                            headers=admin_headers, json=payload)
        assert r.status_code == 200, r.text
        order = r.json()["order"]
        assert order["payment_status"] == expected, (
            f"method={method} mark={mark} got {order['payment_status']}")


# 8) Validation errors
class TestManualOrderValidation:
    def _base_payload(self, item_id: str, addr: dict, slot: dict) -> dict:
        return {
            "new_customer": {"name": "TEST Val",
                             "phone": f"+1 111-555-{uuid.uuid4().int % 9000 + 1000:04d}",
                             "email": _uniq_email("val")},
            "items": [{"kind": "menu", "ref_id": item_id, "quantity": 1}],
            "address": addr,
            "slot": slot,
            "phone": "+1 111-555-2222",
            "payment_method": "cod",
        }

    def test_missing_customer_returns_4xx(
        self, api_client: requests.Session, admin_headers: dict,
        sample_address: dict, sample_slot: dict, menu_item: dict,
    ):
        payload = self._base_payload(menu_item["item_id"], sample_address, sample_slot)
        payload.pop("new_customer")
        r = api_client.post(f"{API}/admin/orders/create",
                            headers=admin_headers, json=payload)
        assert 400 <= r.status_code < 500, r.text

    def test_missing_items_returns_4xx(
        self, api_client: requests.Session, admin_headers: dict,
        sample_address: dict, sample_slot: dict, menu_item: dict,
    ):
        payload = self._base_payload(menu_item["item_id"], sample_address, sample_slot)
        payload["items"] = []
        r = api_client.post(f"{API}/admin/orders/create",
                            headers=admin_headers, json=payload)
        assert 400 <= r.status_code < 500, r.text

    def test_missing_slot_returns_4xx(
        self, api_client: requests.Session, admin_headers: dict,
        sample_address: dict, menu_item: dict,
    ):
        payload = self._base_payload(menu_item["item_id"], sample_address, {})
        r = api_client.post(f"{API}/admin/orders/create",
                            headers=admin_headers, json=payload)
        assert r.status_code == 422, r.text

    def test_missing_address_returns_4xx(
        self, api_client: requests.Session, admin_headers: dict,
        sample_slot: dict, menu_item: dict,
    ):
        payload = self._base_payload(menu_item["item_id"], {}, sample_slot)
        r = api_client.post(f"{API}/admin/orders/create",
                            headers=admin_headers, json=payload)
        assert r.status_code == 422, r.text

    def test_bad_menu_ref_returns_4xx(
        self, api_client: requests.Session, admin_headers: dict,
        sample_address: dict, sample_slot: dict,
    ):
        payload = self._base_payload("mi_does_not_exist", sample_address, sample_slot)
        r = api_client.post(f"{API}/admin/orders/create",
                            headers=admin_headers, json=payload)
        assert 400 <= r.status_code < 500, r.text

    def test_requires_admin_auth(
        self, api_client: requests.Session, sample_address: dict,
        sample_slot: dict, menu_item: dict,
    ):
        r = requests.post(
            f"{API}/admin/orders/create",
            json=self._base_payload(menu_item["item_id"], sample_address, sample_slot),
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code in (401, 403), r.text


# 9) Totals reconciliation across payment methods
class TestTotalsReconciliation:
    def test_totals_match_settings(
        self, api_client: requests.Session, admin_headers: dict,
        order_builder: dict, sample_address: dict, sample_slot: dict,
        menu_item: dict,
    ):
        st = order_builder["settings"]
        delivery_fee = st["delivery_fee_cents"]
        tax_rate_bps = st["tax_rate_bps"]

        phone = f"+1 289-555-{uuid.uuid4().int % 9000 + 1000:04d}"
        payload = {
            "new_customer": {"name": "TEST Totals", "phone": phone,
                             "email": _uniq_email("totals")},
            "items": [{"kind": "menu", "ref_id": menu_item["item_id"], "quantity": 3}],
            "address": sample_address,
            "slot": sample_slot,
            "phone": phone,
            "payment_method": "card",
            "mark_as_paid": True,
        }
        r = api_client.post(f"{API}/admin/orders/create",
                            headers=admin_headers, json=payload)
        assert r.status_code == 200, r.text
        order = r.json()["order"]

        subtotal = menu_item["price_cents"] * 3
        assert order["subtotal_cents"] == subtotal
        assert order["delivery_fee_cents"] == delivery_fee

        # Reconstruct expected tax with the same rule the server uses
        pm_cfg = (st.get("payment_methods") or {}).get("stripe") or {}
        tax_on = pm_cfg.get("tax_enabled", st.get("tax_enabled", True))
        taxable = subtotal + delivery_fee
        expected_tax = (taxable * tax_rate_bps) // 10000 if tax_on else 0
        assert order["tax_cents"] == expected_tax, (
            f"expected {expected_tax} got {order['tax_cents']}")
        assert order["total_cents"] == taxable + expected_tax
        assert order.get("tax_label") == st["tax_label"]


# 10) REGRESSION — null email should NOT crash the endpoint
class TestNullEmailRegression:
    """The modal spec says email is OPTIONAL on inline customer creation
    (name + phone are the only required fields).  However the backend has a
    non-sparse `unique` index on `users.email` (server.py:4494) and inserts
    `email: null` when the field is omitted.  Result: the SECOND phone-only
    customer creation ever attempted returns 500 (E11000 duplicate key on
    { email: null }).  This test PROVES the bug exists so the main agent can
    fix it by (a) converting the index to a partial/sparse index that only
    enforces uniqueness when email is a non-null string, AND (b) omitting
    the `email` field from the insert doc when None (rather than storing
    null).  Existing null-email docs will need to be cleaned up or handled
    by the partial-filter expression.
    """

    def test_two_phone_only_customers_should_both_succeed(
        self, api_client: requests.Session, admin_headers: dict,
    ):
        p1 = f"+1 000-555-{uuid.uuid4().int % 9000 + 1000:04d}"
        p2 = f"+1 000-555-{uuid.uuid4().int % 9000 + 1000:04d}"
        r1 = api_client.post(
            f"{API}/admin/customers",
            headers=admin_headers,
            json={"name": "TEST NullEmail A", "phone": p1},
        )
        r2 = api_client.post(
            f"{API}/admin/customers",
            headers=admin_headers,
            json={"name": "TEST NullEmail B", "phone": p2},
        )
        # Both should succeed; today the second returns 500 (E11000 null email)
        assert r1.status_code == 200, r1.text
        assert r2.status_code == 200, (
            f"REGRESSION: 2nd phone-only customer returned "
            f"{r2.status_code}: {r2.text}"
        )

