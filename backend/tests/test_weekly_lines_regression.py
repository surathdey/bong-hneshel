"""Regression tests for Weekly Menu v2 lines (master-picker refactor).
Ensures backend contracts for line upsert/delete and public /menu/current hydration
remain unchanged after admin UX refactor."""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "https://curry-ecosystem.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@curryandco.local"
ADMIN_PASSWORD = "curry@admin2026"


@pytest.fixture(scope="module")
def admin_token():
    # Seed & login
    requests.post(f"{BASE_URL}/api/dev/seed", timeout=30)
    r = requests.post(f"{BASE_URL}/api/admin/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def current_week(auth_headers):
    r = requests.get(f"{BASE_URL}/api/admin/menus", headers=auth_headers, timeout=30)
    assert r.status_code == 200
    menus = r.json()
    assert isinstance(menus, list) and len(menus) > 0
    return menus[0]  # first week


@pytest.fixture(scope="module")
def master_items(auth_headers):
    r = requests.get(f"{BASE_URL}/api/admin/master-menu?active=true", headers=auth_headers, timeout=30)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list) and len(items) >= 2
    return items


# --- Line upsert contract ------------------------------------------------------
class TestWeeklyLineUpsert:
    def test_line_upsert_with_price_override(self, auth_headers, current_week, master_items):
        # Pick a master item NOT already in the week to avoid collision.
        existing_ids = {ln.get("master_item_id") for ln in (current_week.get("lines") or [])}
        candidate = next((m for m in master_items if m["item_id"] not in existing_ids), master_items[-1])

        line_id = "wl_regression_upsert_001"
        payload = {
            "line": {
                "line_id": line_id,
                "master_item_id": candidate["item_id"],
                "price_override_cents": 1599,
                "availability": "available",
                "stock_limit": None,
                "is_featured": False,
                "display_order": 99,
            }
        }
        r = requests.post(
            f"{BASE_URL}/api/admin/menus/{current_week['week_start']}/lines",
            headers=auth_headers, json=payload, timeout=30,
        )
        assert r.status_code in (200, 201), f"upsert failed: {r.status_code} {r.text}"

        # Verify persistence via GET /admin/menus
        r2 = requests.get(f"{BASE_URL}/api/admin/menus", headers=auth_headers, timeout=30)
        assert r2.status_code == 200
        week = next((m for m in r2.json() if m["week_start"] == current_week["week_start"]), None)
        assert week is not None
        line = next((ln for ln in (week.get("lines") or []) if ln["line_id"] == line_id), None)
        assert line is not None, "line not persisted"
        assert line["master_item_id"] == candidate["item_id"]
        assert line["price_override_cents"] == 1599
        assert line["availability"] == "available"

    def test_line_delete(self, auth_headers, current_week):
        # delete the line created above
        line_id = "wl_regression_upsert_001"
        r = requests.delete(
            f"{BASE_URL}/api/admin/menus/{current_week['week_start']}/lines/{line_id}",
            headers=auth_headers, timeout=30,
        )
        assert r.status_code in (200, 204), f"delete failed: {r.status_code} {r.text}"

        # Verify removal
        r2 = requests.get(f"{BASE_URL}/api/admin/menus", headers=auth_headers, timeout=30)
        week = next((m for m in r2.json() if m["week_start"] == current_week["week_start"]), None)
        assert week is not None
        assert not any(ln["line_id"] == line_id for ln in (week.get("lines") or []))


# --- Public /menu/current hydration -------------------------------------------
class TestMenuCurrentHydration:
    def test_menu_current_hydrates_from_master(self):
        r = requests.get(f"{BASE_URL}/api/menu/current", timeout=30)
        assert r.status_code == 200
        data = r.json()
        # v2 items should be hydrated from master_menu; each item exposes name, image, category
        items = data.get("items") or data.get("lines") or []
        assert isinstance(items, list) and len(items) > 0
        first = items[0]
        # Required hydrated fields
        for field in ("name", "image_url", "category"):
            assert field in first and first[field], f"hydrated field missing: {field}"
        # Price should be in cents
        assert "price_cents" in first
        assert isinstance(first["price_cents"], int)

    def test_price_override_reflected_on_public(self, auth_headers, current_week, master_items):
        existing_ids = {ln.get("master_item_id") for ln in (current_week.get("lines") or [])}
        candidate = next((m for m in master_items if m["item_id"] not in existing_ids), master_items[-1])
        override_cents = 2222
        line_id = "wl_regression_override_002"
        payload = {"line": {
            "line_id": line_id,
            "master_item_id": candidate["item_id"],
            "price_override_cents": override_cents,
            "availability": "available",
            "stock_limit": None,
            "is_featured": False,
            "display_order": 99,
        }}
        r = requests.post(
            f"{BASE_URL}/api/admin/menus/{current_week['week_start']}/lines",
            headers=auth_headers, json=payload, timeout=30,
        )
        assert r.status_code in (200, 201)

        try:
            r2 = requests.get(f"{BASE_URL}/api/menu/current", timeout=30)
            assert r2.status_code == 200
            items = r2.json().get("items") or r2.json().get("lines") or []
            match = next((it for it in items if it.get("line_id") == line_id
                          or it.get("master_item_id") == candidate["item_id"]), None)
            # If current_week isn't the "current" week for /menu/current, skip cleanly
            if match is None:
                pytest.skip("upserted line's week is not the customer 'current' week")
            assert match["price_cents"] == override_cents, "override price not reflected"
        finally:
            requests.delete(
                f"{BASE_URL}/api/admin/menus/{current_week['week_start']}/lines/{line_id}",
                headers=auth_headers, timeout=30,
            )
