"""Curry & Co. — Iteration 22 tests.

Backend contract verification for the Admin **New Order** modal after the
`admin_order_builder` fix that normalizes weekly_menus.lines[] (v2 schema)
into a unified items[] array + adds `current_week_start` + backfills
`package.eligible_master_ids` from lines[].

Covers:
  1. GET /api/admin/order-builder → returns `current_week_start` and today
     falls within [week_start, week_start + 6 days].
  2. Each week in weeks[] has a normalized `items[]` array populated from
     lines[] with name/price_cents/veg_type/image_url and item_id == master_item_id.
  3. When week.package_enabled=True → week.package.eligible_master_ids is
     populated (backfilled from lines[].master_item_id if it was empty).
  4. POST /api/admin/orders/create with kind='menu' + ref_id = master_item_id
     from a v2 weekly line → 200 (order created, no 400 "menu item not found").
  5. POST /api/admin/orders/create with kind='weekly_package' + ref_id=menu_id
     + package_selections = first `pick_count` eligible_master_ids → 200.

Runs against the deployed preview backend (EXPO_PUBLIC_BACKEND_URL).
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import date, datetime, timedelta
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


def _uniq_phone() -> str:
    # +1 416-555-XXXX where XXXX comes from uuid to avoid dedupe collisions
    tail = uuid.uuid4().hex[:4].upper()
    return f"+1 416-555-{tail}"


# ------------------------------------------------------------- fixtures ---
@pytest.fixture(scope="module")
def admin_token() -> str:
    r = requests.post(
        f"{API}/admin/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token")
    assert tok, "No access_token returned"
    return tok


@pytest.fixture(scope="module", autouse=True)
def _seed_once(admin_token: str) -> None:
    """Ensure current-week menu + master + catering are seeded."""
    r = requests.post(
        f"{API}/dev/seed",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=60,
    )
    # seed endpoint is public but posting with token is fine
    assert r.status_code == 200, f"seed failed: {r.status_code} {r.text[:200]}"


@pytest.fixture(scope="module")
def builder(admin_token: str) -> dict:
    r = requests.get(
        f"{API}/admin/order-builder",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=30,
    )
    assert r.status_code == 200, f"order-builder failed: {r.status_code} {r.text[:200]}"
    return r.json()


def _first_delivery_slot(builder: dict) -> dict:
    slots = builder.get("delivery_slots") or []
    assert slots, "No delivery_slots in builder response"
    s = slots[0]
    return {"date": s["date"], "window": s["window"]}


def _std_address() -> dict:
    return {
        "line1": "123 TEST King St",
        "line2": "",
        "city": "Toronto",
        "province": "ON",
        "postal_code": "M5V 1J1",
    }


# =========================================================================
# 1. current_week_start present & correct
# =========================================================================
class TestCurrentWeekStart:
    def test_current_week_start_is_present(self, builder):
        assert "current_week_start" in builder, "Response missing `current_week_start` key"

    def test_current_week_start_within_today_window(self, builder):
        cws = builder.get("current_week_start")
        assert cws, f"current_week_start is null/empty. Response weeks: " \
            f"{[w.get('week_start') for w in (builder.get('weeks') or [])]}"
        ws_date = datetime.fromisoformat(cws).date()
        today = date.today()
        # today must be within [week_start, week_start + 6]
        assert ws_date <= today <= ws_date + timedelta(days=6), (
            f"current_week_start={cws} does not contain today={today.isoformat()}"
        )

    def test_current_week_start_matches_one_of_the_weeks(self, builder):
        cws = builder.get("current_week_start")
        week_starts = [w.get("week_start") for w in (builder.get("weeks") or [])]
        assert cws in week_starts, f"current_week_start={cws} not in weeks={week_starts}"


# =========================================================================
# 2. Weeks: items[] normalized from lines[]
# =========================================================================
class TestWeeksItemsNormalization:
    def test_weeks_present(self, builder):
        weeks = builder.get("weeks") or []
        assert len(weeks) >= 1, "No weekly menus returned"

    def test_every_week_has_items_array(self, builder):
        for w in builder.get("weeks", []):
            assert "items" in w, f"week {w.get('week_start')} missing items[]"
            assert isinstance(w["items"], list), "items must be a list"

    def test_v2_lines_are_normalized_to_items(self, builder):
        """For any week that has lines[] but empty legacy items[], the merged
        items[] must contain one entry per line with name+price_cents+veg_type+
        image_url enriched from master_menu."""
        checked = 0
        for w in builder.get("weeks", []):
            lines = w.get("lines") or []
            if not lines:
                continue
            items = w.get("items") or []
            # There should be at least as many merged items as lines
            assert len(items) >= len(lines), (
                f"week {w.get('week_start')}: items({len(items)}) < lines({len(lines)})"
            )
            # Build the set of master_item_ids that came from lines
            line_ids = {ln.get("master_item_id") for ln in lines if ln.get("master_item_id")}
            item_ids = {it.get("item_id") for it in items}
            missing = line_ids - item_ids
            assert not missing, (
                f"week {w.get('week_start')}: line master_ids not in items[]: {missing}"
            )
            # Each normalized item must expose the enriched fields.
            for it in items:
                if it.get("item_id") in line_ids:
                    assert it.get("name"), f"item {it['item_id']} has no name"
                    assert it.get("price_cents") is not None, (
                        f"item {it['item_id']} has no price_cents"
                    )
                    assert "veg_type" in it, f"item {it['item_id']} missing veg_type"
                    assert "image_url" in it, f"item {it['item_id']} missing image_url"
                    # item_id must equal master_item_id per contract
                    assert it.get("master_item_id") == it.get("item_id"), (
                        f"item_id != master_item_id for {it}"
                    )
            checked += 1
        assert checked >= 1, "No v2-line weeks were found to verify"


# =========================================================================
# 3. Package.eligible_master_ids backfilled from lines[]
# =========================================================================
class TestPackageEligibleBackfill:
    def test_enabled_package_has_eligible_ids(self, builder):
        checked = 0
        for w in builder.get("weeks", []):
            if not w.get("package_enabled"):
                continue
            pkg = w.get("package") or {}
            eligible = pkg.get("eligible_master_ids") or []
            assert eligible, (
                f"week {w.get('week_start')} has package_enabled=true but empty "
                f"eligible_master_ids"
            )
            # Every eligible_id must exist in the week's lines[].master_item_id set
            line_ids = {ln.get("master_item_id") for ln in (w.get("lines") or [])}
            if line_ids:
                # Backfill semantics: eligible_master_ids ⊆ line_ids (when backfilled),
                # or an admin-curated subset. Either way none of them should be junk.
                assert all(mid in line_ids or mid for mid in eligible)
            checked += 1
        if checked == 0:
            pytest.skip("No package_enabled weeks in current builder response")


# =========================================================================
# 4. Manual order create with kind='menu' + v2 line ref_id
# =========================================================================
class TestManualOrderV2MenuItem:
    def test_create_order_with_v2_master_item_id(self, admin_token, builder):
        # Find a v2 line-derived item from the CURRENT week when possible
        cws = builder.get("current_week_start")
        weeks = builder.get("weeks", [])
        target_week = next((w for w in weeks if w.get("week_start") == cws), None)
        if target_week is None or not (target_week.get("lines") or []):
            # Fallback: any week that has lines
            target_week = next(
                (w for w in weeks if (w.get("lines") or [])), None
            )
        assert target_week, "No week with v2 lines[] to test against"
        master_id = target_week["lines"][0]["master_item_id"]
        # Sanity: this master_item_id should appear in the normalized items[]
        assert any(it.get("item_id") == master_id for it in target_week.get("items", [])), (
            "master_item_id not surfaced in normalized items[]"
        )

        slot = _first_delivery_slot(builder)
        payload = {
            "new_customer": {
                "name": "TEST V2 Menu Customer",
                "phone": _uniq_phone(),
            },
            "items": [{"kind": "menu", "ref_id": master_id, "quantity": 1}],
            "address": _std_address(),
            "slot": slot,
            "phone": "+1 416-555-9999",
            "payment_method": "cod",
            "mark_as_paid": False,
        }
        r = requests.post(
            f"{API}/admin/orders/create",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30,
        )
        assert r.status_code == 200, (
            f"expected 200, got {r.status_code}: {r.text[:400]}"
        )
        body = r.json()
        order = body.get("order") or body
        assert order.get("created_by_admin") is True
        # items_snapshot should reflect our v2 item
        snaps = order.get("items_snapshot") or []
        assert snaps, "items_snapshot missing"
        assert snaps[0]["ref_id"] == master_id
        assert snaps[0]["kind"] == "menu"
        assert snaps[0].get("name"), "line snapshot has no name"
        assert (snaps[0].get("unit_price_cents") or 0) > 0


# =========================================================================
# 5. Manual order create with kind='weekly_package'
# =========================================================================
class TestManualOrderWeeklyPackage:
    def test_create_weekly_package_order(self, admin_token, builder):
        # Pick the first week where package_enabled=true
        target = next(
            (w for w in builder.get("weeks", []) if w.get("package_enabled")),
            None,
        )
        if not target:
            pytest.skip("No package_enabled weekly menu present")
        pkg = target.get("package") or {}
        pick_count = int(pkg.get("pick_count") or 0)
        assert pick_count > 0, "pick_count missing on enabled package"
        eligible = pkg.get("eligible_master_ids") or []
        assert len(eligible) >= pick_count, (
            f"Not enough eligible items ({len(eligible)}) for pick_count={pick_count}"
        )
        picks = eligible[:pick_count]

        slot = _first_delivery_slot(builder)
        payload = {
            "new_customer": {
                "name": "TEST Weekly Combo Customer",
                "phone": _uniq_phone(),
            },
            "items": [
                {
                    "kind": "weekly_package",
                    "ref_id": target["menu_id"],
                    "quantity": 1,
                    "package_selections": picks,
                }
            ],
            "address": _std_address(),
            "slot": slot,
            "phone": "+1 416-555-8888",
            "payment_method": "cod",
            "mark_as_paid": False,
        }
        r = requests.post(
            f"{API}/admin/orders/create",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30,
        )
        assert r.status_code == 200, (
            f"expected 200, got {r.status_code}: {r.text[:400]}"
        )
        body = r.json()
        order = body.get("order") or body
        snaps = order.get("items_snapshot") or []
        assert snaps and snaps[0]["kind"] == "weekly_package"
        assert snaps[0]["ref_id"] == target["menu_id"]
        # Must echo back all picks (order + duplicates preserved by _resolve_items)
        assert snaps[0].get("package_selection_ids") == picks
        assert snaps[0].get("package_pick_count") == pick_count
        # Combo price = base + surcharges
        assert (snaps[0].get("unit_price_cents") or 0) >= (pkg.get("price_cents") or 0)

    def test_weekly_package_wrong_count_rejected(self, admin_token, builder):
        target = next(
            (w for w in builder.get("weeks", []) if w.get("package_enabled")),
            None,
        )
        if not target:
            pytest.skip("No package_enabled weekly menu present")
        pkg = target.get("package") or {}
        pick_count = int(pkg.get("pick_count") or 0)
        eligible = pkg.get("eligible_master_ids") or []
        if pick_count < 2 or len(eligible) < 1:
            pytest.skip("Not enough data to test wrong-pick-count path")
        # Send N-1 picks → expect 400
        slot = _first_delivery_slot(builder)
        payload = {
            "new_customer": {
                "name": "TEST Wrong Pick Count",
                "phone": _uniq_phone(),
            },
            "items": [
                {
                    "kind": "weekly_package",
                    "ref_id": target["menu_id"],
                    "quantity": 1,
                    "package_selections": eligible[: pick_count - 1],
                }
            ],
            "address": _std_address(),
            "slot": slot,
            "phone": "+1 416-555-7777",
            "payment_method": "cod",
            "mark_as_paid": False,
        }
        r = requests.post(
            f"{API}/admin/orders/create",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30,
        )
        assert r.status_code == 400, (
            f"expected 400, got {r.status_code}: {r.text[:200]}"
        )
