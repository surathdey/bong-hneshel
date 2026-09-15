"""Catering v2 end-to-end backend tests.

Covers seed, list, detail, quote/order validation, custom quote request,
and admin CRUD for the Catering v2 schema.
"""
import os
import re
from pathlib import Path

import pytest
import requests
from pymongo import MongoClient


def _load_frontend_env():
    env = Path("/app/frontend/.env")
    if env.exists():
        for line in env.read_text().splitlines():
            m = re.match(r'^\s*([A-Z0-9_]+)\s*=\s*"?([^"\s]+)"?\s*$', line)
            if m:
                os.environ.setdefault(m.group(1), m.group(2))


_load_frontend_env()
BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    os.environ.get("EXPO_BACKEND_URL", ""),
).rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "curry_co_db")

ADMIN_EMAIL = "admin@curryandco.local"
ADMIN_PASSWORD = "curry@admin2026"


# ------------------ fixtures ------------------
@pytest.fixture(scope="session")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def mongo_db():
    c = MongoClient(MONGO_URL, serverSelectionTimeoutMS=3000)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="session", autouse=True)
def _seed(api_client):
    r = api_client.post(f"{API}/dev/seed")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert body.get("packages") == 5, f"expected 5 packages seeded: {body}"
    # master_items must be at least 40 per review request
    assert body.get("master_items", 0) >= 40, f"expected >=40 master items: {body}"


@pytest.fixture()
def guest(api_client, mongo_db):
    r = api_client.post(f"{API}/auth/guest")
    assert r.status_code == 200, r.text
    data = r.json()
    yield data
    uid = data["user"]["user_id"]
    mongo_db.user_sessions.delete_many({"user_id": uid})
    mongo_db.users.delete_one({"user_id": uid})
    mongo_db.orders.delete_many({"user_id": uid})


@pytest.fixture()
def guest_headers(guest):
    return {"Authorization": f"Bearer {guest['session_token']}",
            "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def admin_headers(api_client):
    r = api_client.post(f"{API}/admin/login",
                        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}",
            "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def packages(api_client):
    r = api_client.get(f"{API}/catering")
    assert r.status_code == 200
    pkgs = r.json()
    assert isinstance(pkgs, list)
    return pkgs


def _addr_slot():
    return {
        "address": {"line1": "1 King", "line2": "", "city": "Toronto",
                    "province": "ON", "postal_code": "M5V1A1"},
        "slot": {"date": "2099-01-30", "window": "friday_evening"},
        "coupon_code": None,
        "redeem_points": 0,
        "special_instructions": "TEST_v2",
        "payment_method": "cod",
        "phone": "6470001234",
    }


# =========================================================
# 1. Seed + list contract
# =========================================================
class TestSeedAndList:
    def test_five_packages_returned_and_sorted(self, packages):
        assert len(packages) == 5, f"expected 5, got {len(packages)}"
        sort_orders = [p.get("sort_order", 0) for p in packages]
        assert sort_orders == sorted(sort_orders), \
            f"packages not sorted by sort_order: {sort_orders}"

    def test_pkg1_snack_box_shape(self, packages):
        p1 = packages[0]
        assert p1["name"] == "Kolkata Adda Snack Box"
        assert len(p1.get("upgrade_tiers", [])) == 2, \
            f"expected 2 tiers: {p1.get('upgrade_tiers')}"
        assert len(p1.get("choice_groups", [])) == 2, \
            f"expected 2 choice groups: {p1.get('choice_groups')}"
        # Default tier is base $9
        default = next((t for t in p1["upgrade_tiers"] if t.get("is_default")), None)
        assert default and default["per_person_cents"] == 900

    def test_pkg2_sunday_lunch_has_premium(self, packages):
        p2 = packages[1]
        assert "Sunday" in p2["name"]
        prem = p2.get("premium_items", [])
        assert len(prem) == 1, f"expected 1 premium item: {prem}"
        assert prem[0]["upcharge_per_person_cents"] == 400

    def test_pkg5_shonar_bangla_is_custom_quote(self, packages):
        p5 = packages[4]
        assert "Shonar" in p5["name"]
        assert p5.get("is_custom_quote") is True
        assert p5.get("price_cents") == 0


# =========================================================
# 2. Detail endpoint: master_items map is complete
# =========================================================
class TestCateringDetail:
    def test_master_items_map_covers_all_refs(self, api_client, packages):
        for pkg in packages:
            r = api_client.get(f"{API}/catering/{pkg['package_id']}")
            assert r.status_code == 200, r.text
            d = r.json()
            assert "package" in d and "master_items" in d
            master = d["master_items"]
            # Collect referenced IDs
            ref = set()
            for g in d["package"].get("choice_groups", []) or []:
                ref.update(g.get("option_master_ids", []) or [])
            ref.update(d["package"].get("included_master_ids") or [])
            ref.update(p["master_item_id"] for p in (d["package"].get("premium_items") or []))
            missing = [rid for rid in ref if rid not in master]
            assert not missing, \
                f"master_items missing IDs for pkg {pkg['name']}: {missing}"
            # Sanity: each master entry has key fields
            for mid, m in master.items():
                assert m.get("name")
                assert "veg_type" in m
                assert "category" in m
                assert "image_url" in m

    def test_detail_404_for_bad_id(self, api_client):
        r = api_client.get(f"{API}/catering/does-not-exist")
        assert r.status_code == 404


# =========================================================
# 3. Order quote / create validation
# =========================================================
class TestCateringQuoteAndOrder:
    def _pkg(self, packages, name_substr):
        for p in packages:
            if name_substr in p["name"]:
                return p
        pytest.fail(f"pkg with '{name_substr}' not found")

    def test_reject_below_min_guests(self, api_client, guest_headers, packages):
        pkg = self._pkg(packages, "Kolkata Adda Snack Box")
        # pick default tier's snack+tea groups minimally
        default_tier = next(t for t in pkg["upgrade_tiers"] if t.get("is_default"))
        sel = {
            "tier_id": default_tier["tier_id"],
            "group_selections": {
                g["group_id"]: g["option_master_ids"][:1] for g in pkg["choice_groups"]
            },
        }
        payload = _addr_slot()
        payload["items"] = [{
            "kind": "catering", "ref_id": pkg["package_id"], "quantity": 1,
            "catering_guest_count": 1,  # below min (10)
            "catering_selections": sel,
        }]
        r = api_client.post(f"{API}/orders/quote", json=payload, headers=guest_headers)
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"

    def test_reject_wrong_choice_count(self, api_client, guest_headers, packages):
        pkg = self._pkg(packages, "Sunday Bari'r Lunch")
        # Need 3 veg but supply 1
        veg_group = next(g for g in pkg["choice_groups"] if "Veg" in g["title"])
        sel = {
            "group_selections": {veg_group["group_id"]: veg_group["option_master_ids"][:1]},
        }
        # Also need to satisfy other groups minimally to make sure failure is about veg
        for g in pkg["choice_groups"]:
            if g["group_id"] != veg_group["group_id"]:
                sel["group_selections"][g["group_id"]] = g["option_master_ids"][: g["min_select"]]
        payload = _addr_slot()
        payload["items"] = [{
            "kind": "catering", "ref_id": pkg["package_id"], "quantity": 1,
            "catering_guest_count": 10,
            "catering_selections": sel,
        }]
        r = api_client.post(f"{API}/orders/quote", json=payload, headers=guest_headers)
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"

    def test_reject_custom_quote_order(self, api_client, guest_headers, packages):
        pkg = self._pkg(packages, "Shonar Bangla")
        payload = _addr_slot()
        payload["items"] = [{
            "kind": "catering", "ref_id": pkg["package_id"], "quantity": 1,
            "catering_guest_count": 30,
            "catering_selections": {"group_selections": {}},
        }]
        r = api_client.post(f"{API}/orders/quote", json=payload, headers=guest_headers)
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"
        assert "quote" in r.text.lower()

    def test_snack_box_default_tier(self, api_client, guest_headers, packages):
        pkg = self._pkg(packages, "Kolkata Adda Snack Box")
        default_tier = next(t for t in pkg["upgrade_tiers"] if t.get("is_default"))
        sel = {
            "tier_id": default_tier["tier_id"],
            "group_selections": {
                g["group_id"]: g["option_master_ids"][:1]  # 1 pick each (min=max=1)
                for g in pkg["choice_groups"]
            },
        }
        payload = _addr_slot()
        payload["items"] = [{
            "kind": "catering", "ref_id": pkg["package_id"], "quantity": 1,
            "catering_guest_count": 10,
            "catering_selections": sel,
        }]
        r = api_client.post(f"{API}/orders/quote", json=payload, headers=guest_headers)
        assert r.status_code == 200, r.text
        q = r.json()
        # 900 cents * 10 = 9000
        assert q["subtotal_cents"] == 9000, f"expected 9000 got {q['subtotal_cents']}: {q}"

    def test_snack_box_upgrade_tier_requires_two_snacks(self, api_client, guest_headers, packages):
        pkg = self._pkg(packages, "Kolkata Adda Snack Box")
        upgrade_tier = next(t for t in pkg["upgrade_tiers"] if not t.get("is_default"))
        # Snack group needs 2 picks in this tier
        snack_group = next(g for g in pkg["choice_groups"] if g["title"] == "Snack")
        tea_group = next(g for g in pkg["choice_groups"] if g["group_id"] != snack_group["group_id"])
        # First try with only 1 snack -> 400
        bad_sel = {
            "tier_id": upgrade_tier["tier_id"],
            "group_selections": {
                snack_group["group_id"]: snack_group["option_master_ids"][:1],
                tea_group["group_id"]: tea_group["option_master_ids"][:1],
            },
        }
        payload = _addr_slot()
        payload["items"] = [{
            "kind": "catering", "ref_id": pkg["package_id"], "quantity": 1,
            "catering_guest_count": 10, "catering_selections": bad_sel,
        }]
        r = api_client.post(f"{API}/orders/quote", json=payload, headers=guest_headers)
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"

        # Now with 2 snacks -> OK, price is $12*10=12000
        good_sel = {
            "tier_id": upgrade_tier["tier_id"],
            "group_selections": {
                snack_group["group_id"]: snack_group["option_master_ids"][:2],
                tea_group["group_id"]: tea_group["option_master_ids"][:1],
            },
        }
        payload["items"][0]["catering_selections"] = good_sel
        r2 = api_client.post(f"{API}/orders/quote", json=payload, headers=guest_headers)
        assert r2.status_code == 200, r2.text
        q = r2.json()
        assert q["subtotal_cents"] == 12000, f"expected 12000 got {q['subtotal_cents']}"

    def test_sunday_lunch_premium_upcharge(self, api_client, guest_headers, packages):
        pkg = self._pkg(packages, "Sunday Bari'r Lunch")
        prem = pkg["premium_items"][0]
        sel = {
            "group_selections": {
                g["group_id"]: g["option_master_ids"][: g["min_select"]]
                for g in pkg["choice_groups"]
            },
            "premium_selections": [prem["master_item_id"]],
        }
        payload = _addr_slot()
        payload["items"] = [{
            "kind": "catering", "ref_id": pkg["package_id"], "quantity": 1,
            "catering_guest_count": 10, "catering_selections": sel,
        }]
        r = api_client.post(f"{API}/orders/quote", json=payload, headers=guest_headers)
        assert r.status_code == 200, r.text
        q = r.json()
        # (2499 + 400) * 10 = 28990
        expected = (pkg["price_cents"] + prem["upcharge_per_person_cents"]) * 10
        assert q["subtotal_cents"] == expected, \
            f"expected {expected} got {q['subtotal_cents']}: {q}"

    def test_order_snapshot_has_selection_summary(self, api_client, guest_headers, packages):
        pkg = self._pkg(packages, "Sunday Bari'r Lunch")
        sel = {
            "group_selections": {
                g["group_id"]: g["option_master_ids"][: g["min_select"]]
                for g in pkg["choice_groups"]
            },
        }
        payload = _addr_slot()
        payload["items"] = [{
            "kind": "catering", "ref_id": pkg["package_id"], "quantity": 1,
            "catering_guest_count": 12, "catering_selections": sel,
        }]
        r = api_client.post(f"{API}/orders", json=payload, headers=guest_headers)
        assert r.status_code == 200, r.text
        order = r.json()
        snap = order.get("items_snapshot", [])
        assert snap and snap[0]["kind"] == "catering"
        summary = snap[0].get("selection_summary")
        assert isinstance(summary, list) and len(summary) == len(pkg["choice_groups"]), \
            f"selection_summary shape wrong: {summary}"
        for row in summary:
            assert "title" in row and "items" in row
            assert isinstance(row["items"], list) and len(row["items"]) >= 1


# =========================================================
# 4. Custom quote request endpoint
# =========================================================
class TestCateringQuoteRequest:
    def test_stores_request(self, api_client, mongo_db, packages):
        pkg = next(p for p in packages if "Shonar" in p["name"])
        payload = {
            "package_id": pkg["package_id"],
            "name": "TEST User",
            "email": "test@example.com",
            "phone": "6470005555",
            "guest_count": 60,
            "event_date": "2099-05-15",
            "notes": "TEST notes",
        }
        r = api_client.post(f"{API}/catering/quote-request", json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        rid = d["request_id"]
        # Persisted?
        doc = mongo_db.catering_quote_requests.find_one({"request_id": rid})
        assert doc, "quote-request not persisted"
        assert doc["guest_count"] == 60
        assert doc["status"] == "new"
        mongo_db.catering_quote_requests.delete_one({"request_id": rid})


# =========================================================
# 5. Admin catering endpoints
# =========================================================
class TestAdminCateringV2:
    def test_admin_list_five_sorted(self, api_client, admin_headers):
        r = api_client.get(f"{API}/admin/catering", headers=admin_headers)
        assert r.status_code == 200, r.text
        pkgs = r.json()
        assert len(pkgs) == 5
        sos = [p.get("sort_order", 0) for p in pkgs]
        assert sos == sorted(sos)

    def test_admin_upsert_v2_schema(self, api_client, admin_headers, mongo_db):
        # Grab a real master item id to reference
        mi = mongo_db.master_menu.find_one({}, {"_id": 0, "item_id": 1})
        assert mi
        mid = mi["item_id"]
        pkg = {
            "name": "TEST_v2_pkg",
            "tagline": "TEST",
            "description": "TEST desc",
            "emoji": "🧪",
            "perfect_for": "TEST",
            "price_cents": 1500,
            "min_guests": 8,
            "image_url": "https://x/y.jpg",
            "includes": ["TEST inc"],
            "included_master_ids": [mid],
            "choice_groups": [{
                "title": "TEST Group", "subtitle": "pick 1",
                "min_select": 1, "max_select": 1,
                "option_master_ids": [mid], "display_order": 0,
            }],
            "upgrade_tiers": [{
                "title": "Base", "subtitle": "base",
                "per_person_cents": 1500, "is_default": True,
                "group_overrides": {},
            }],
            "premium_items": [{
                "master_item_id": mid, "upcharge_per_person_cents": 200,
            }],
            "is_custom_quote": False,
            "sort_order": 99,
        }
        r = api_client.post(f"{API}/admin/catering", json=pkg, headers=admin_headers)
        assert r.status_code == 200, r.text
        created = r.json()
        pid = (created.get("package_id")
               or created.get("package", {}).get("package_id"))
        assert pid, f"no package_id: {created}"

        # Fetch via public list & verify v2 fields survived roundtrip
        got = next((p for p in api_client.get(f"{API}/admin/catering",
                                              headers=admin_headers).json()
                    if p["package_id"] == pid), None)
        assert got
        assert got["choice_groups"] and got["choice_groups"][0]["title"] == "TEST Group"
        assert got["upgrade_tiers"] and got["upgrade_tiers"][0]["per_person_cents"] == 1500
        assert got["premium_items"][0]["upcharge_per_person_cents"] == 200
        assert got["included_master_ids"] == [mid]

        rd = api_client.delete(f"{API}/admin/catering/{pid}", headers=admin_headers)
        assert rd.status_code == 200
        mongo_db.catering_packages.delete_many({"package_id": pid})
