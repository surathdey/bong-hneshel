"""
Iteration 19 — Weekly Menu Enhancements backend regression.

Covers the new endpoints/behaviours in the review request:
- POST /admin/menus/create (with copy_all_master → HIDDEN lines) and duplicate 400
- POST /admin/menus/{week}/complimentary
- POST /admin/menus/{week}/lines/{line_id}/visibility (hydrate visibility gating)
- POST/GET /admin/always-available (global list) + /menu/anytime reflects
- /menu/upcoming: complimentary_items populated only when package_enabled
- Cleanup: delete the test week and reset the always list.

Uses the PUBLIC EXPO_PUBLIC_BACKEND_URL so we exercise the ingress just like the app.
"""

import os
import datetime as dt

import pytest
import requests


BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL")
            or "https://garden-template-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@mustardgarden.ca"
ADMIN_PASS = "tlUYkZz1JnsD%Wy2"

# Sunday in the far future, so we don't clobber the live current week.
TEST_WEEK = dt.date(2027, 1, 10).isoformat()  # a Sunday


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{API}/admin/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
                      timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token")
    assert tok, r.text
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module", autouse=True)
def _cleanup_before_and_after(admin_headers):
    # ensure the target test week and always-list are clean before AND after
    prior = requests.get(f"{API}/admin/always-available",
                         headers=admin_headers, timeout=10)
    prior_ids = prior.json().get("master_ids", []) if prior.status_code == 200 else []
    requests.delete(f"{API}/admin/menus/{TEST_WEEK}",
                    headers=admin_headers, timeout=10)
    requests.post(f"{API}/admin/always-available",
                  headers=admin_headers, json={"master_ids": []}, timeout=10)
    yield
    requests.delete(f"{API}/admin/menus/{TEST_WEEK}",
                    headers=admin_headers, timeout=10)
    # restore prior always-list so we don't leave state dirty
    requests.post(f"{API}/admin/always-available",
                  headers=admin_headers,
                  json={"master_ids": prior_ids}, timeout=10)


# --- basic health / auth ------------------------------------------------------

def test_admin_login(admin_headers):
    assert admin_headers["Authorization"].startswith("Bearer ")


def test_master_menu_reachable(admin_headers):
    r = requests.get(f"{API}/admin/master-menu",
                     headers=admin_headers, timeout=15)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list) and len(items) > 0


# --- create week with copy_all_master (all lines hidden by default) -----------

def test_create_week_copyall_produces_hidden_lines(admin_headers):
    r = requests.post(f"{API}/admin/menus/create",
                      headers=admin_headers,
                      json={"week_start": TEST_WEEK, "copy_all_master": True},
                      timeout=20)
    assert r.status_code == 200, r.text
    menu = r.json()["menu"]
    assert menu["week_start"] == TEST_WEEK
    assert menu["title"] == f"Week of {TEST_WEEK}"
    lines = menu["lines"]
    assert len(lines) >= 1, "copy_all_master must seed lines"
    assert all(l["is_visible"] is False for l in lines), \
        "all copied lines must be HIDDEN"
    # alphabetical ordering by display_order
    orders = [l["display_order"] for l in lines]
    assert orders == sorted(orders)


def test_duplicate_create_returns_400(admin_headers):
    r = requests.post(f"{API}/admin/menus/create",
                      headers=admin_headers,
                      json={"week_start": TEST_WEEK}, timeout=15)
    assert r.status_code == 400, r.text


# --- complimentary + package gating ------------------------------------------

def _get_menu(admin_headers):
    r = requests.get(f"{API}/admin/menus",
                     headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text
    for m in r.json():
        if m.get("week_start") == TEST_WEEK:
            return m
    raise AssertionError(f"week {TEST_WEEK} not found in /admin/menus")


def test_complimentary_hidden_when_package_disabled(admin_headers):
    menu = _get_menu(admin_headers)
    lines = menu["lines"]
    mids = [l["master_item_id"] for l in lines[:2]]
    r = requests.post(f"{API}/admin/menus/{TEST_WEEK}/complimentary",
                      headers=admin_headers,
                      json={"master_ids": mids}, timeout=15)
    assert r.status_code == 200, r.text
    # package NOT enabled yet -> complimentary_items must be empty in hydrate
    ups = requests.get(f"{API}/menu/upcoming", timeout=15).json()
    wk = next((x for x in ups if x["week_start"] == TEST_WEEK), None)
    assert wk is not None, "test week must appear in /menu/upcoming"
    assert wk.get("complimentary_items", []) == [], \
        "complimentary_items must be empty when package_enabled=False"


def test_visibility_toggle_and_complimentary_when_package_enabled(admin_headers):
    menu = _get_menu(admin_headers)
    lines = menu["lines"]
    mids = [l["master_item_id"] for l in lines[:2]]
    # enable package
    rp = requests.post(f"{API}/admin/menus/{TEST_WEEK}/settings",
                       headers=admin_headers,
                       json={
                           "package_enabled": True,
                           "package": {
                               "name": "Combo",
                               "pick_count": 3,
                               "price_cents": 3499,
                               "eligible_master_ids": [],
                           },
                       }, timeout=15)
    assert rp.status_code == 200, rp.text

    # ensure complimentary still set
    requests.post(f"{API}/admin/menus/{TEST_WEEK}/complimentary",
                  headers=admin_headers,
                  json={"master_ids": mids}, timeout=15)

    # flip visibility of the first line
    lid = lines[0]["line_id"]
    r = requests.post(
        f"{API}/admin/menus/{TEST_WEEK}/lines/{lid}/visibility",
        headers=admin_headers, json={"is_visible": True}, timeout=15,
    )
    assert r.status_code == 200
    assert r.json()["is_visible"] is True

    ups = requests.get(f"{API}/menu/upcoming", timeout=15).json()
    wk = next((x for x in ups if x["week_start"] == TEST_WEEK), None)
    assert wk is not None
    vis = wk.get("items", [])
    assert len(vis) == 1, f"expected exactly 1 visible item, got {len(vis)}"
    comps = wk.get("complimentary_items", [])
    assert len(comps) == 2, f"expected 2 complimentary items, got {len(comps)}"
    comp_names = [c.get("name") for c in comps]
    assert all(comp_names), "complimentary items must have names"


def test_visibility_toggle_nonexistent_line_returns_404(admin_headers):
    r = requests.post(
        f"{API}/admin/menus/{TEST_WEEK}/lines/does-not-exist/visibility",
        headers=admin_headers, json={"is_visible": True}, timeout=10,
    )
    assert r.status_code == 404


# --- global always-available -------------------------------------------------

def test_always_available_set_and_reflect_on_menu_anytime(admin_headers):
    menu = _get_menu(admin_headers)
    mids = [l["master_item_id"] for l in menu["lines"][:2]]

    r = requests.post(f"{API}/admin/always-available",
                      headers=admin_headers,
                      json={"master_ids": mids}, timeout=15)
    assert r.status_code == 200, r.text
    assert set(r.json()["master_ids"]) == set(mids)

    g = requests.get(f"{API}/admin/always-available",
                     headers=admin_headers, timeout=10)
    assert g.status_code == 200
    assert set(g.json()["master_ids"]) == set(mids)

    anytime = requests.get(f"{API}/menu/anytime", timeout=15).json()
    assert isinstance(anytime, list)
    assert len(anytime) == 2, f"expected 2 anytime dishes, got {len(anytime)}"
    names = [d.get("name") for d in anytime]
    assert all(names)


def test_always_available_empty_falls_back_to_legacy_flag(admin_headers):
    # clear the global list; /menu/anytime should now come from the legacy
    # always_available master flag path (may be 0..N depending on data — just
    # assert it doesn't error and returns a list).
    r = requests.post(f"{API}/admin/always-available",
                      headers=admin_headers,
                      json={"master_ids": []}, timeout=15)
    assert r.status_code == 200
    a = requests.get(f"{API}/menu/anytime", timeout=15)
    assert a.status_code == 200
    assert isinstance(a.json(), list)


# --- /menu/current sanity (still returns visible-only if applicable) ---------

def test_menu_current_returns_only_visible_items():
    """Live current week shouldn't leak hidden lines. Any items returned must
    have master_id/name (proxy for 'hydrated & visible'). This is a smoke test —
    we don't know how many are visible in production data."""
    r = requests.get(f"{API}/menu/current", timeout=15)
    assert r.status_code == 200
    data = r.json()
    # /menu/current returns a dict-shaped payload (may be None if no week)
    if data:
        items = data.get("items", [])
        assert isinstance(items, list)
        for it in items:
            # /menu/current hydrates with item_id + name (not master_id)
            assert it.get("item_id") and it.get("name"), \
                "hydrated item missing name/item_id"
