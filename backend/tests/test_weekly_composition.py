"""
Backend tests for Weekly Meal Plan v3 (Composition-based pricing).
Covers:
  - GET /api/menu/current returns package with composition prices, 10 eligible items,
    and complimentary_items (Gur er Payesh + Dal of the Week)
  - GET /api/menu/anytime returns 7 order-anytime items with image + price
  - POST /api/orders/quote (weekly_package, pick_count=5) composition pricing:
      5 veg          -> 6499
      3 veg + 2 nv   -> 6999 (mix)
      5 nv           -> 7999
      1 egg + 4 veg  -> 6999 (egg counts as non-veg)
      4 picks        -> 400 (must be exactly 5)
      6 picks        -> 400
  - Guest auth via POST /api/auth/guest
  - Admin can PATCH /admin/menus/{ws}/settings to change the 3 composition prices;
    values persist across GETs; then restore.
  - COD order placement with weekly_package (5 picks) succeeds & subtotal is correct.
"""
import os
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL", "")).rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@mustardgarden.ca"
ADMIN_PASSWORD = "tlUYkZz1JnsD%Wy2"


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def current_menu(client):
    r = client.get(f"{API}/menu/current")
    assert r.status_code == 200, r.text
    m = r.json()
    assert m is not None
    return m


@pytest.fixture(scope="module")
def admin_token(client):
    r = client.post(f"{API}/admin/login",
                    json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_hdr(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def guest_token(client):
    r = client.post(f"{API}/auth/guest")
    assert r.status_code == 200, r.text
    tok = r.json().get("session_token") or r.json().get("access_token")
    assert tok, r.text
    return tok


@pytest.fixture(scope="module")
def guest_hdr(guest_token):
    return {"Authorization": f"Bearer {guest_token}", "Content-Type": "application/json"}


# ---------- helpers ----------
def _addr():
    return {"line1": "1 Bay St", "city": "Toronto", "province": "ON", "postal_code": "M5H2N2"}


def _slot():
    return {"date": "2026-01-30", "window": "friday_evening"}


def _split_items(menu):
    veg = [it for it in menu["items"] if it["veg_type"] == "vegetarian"]
    nv = [it for it in menu["items"] if it["veg_type"] == "non-vegetarian"]
    egg = [it for it in menu["items"] if it["veg_type"] == "eggitarian"]
    return veg, nv, egg


# ---------- 1. /menu/current ----------
class TestMenuCurrent:
    def test_package_composition_shape(self, current_menu):
        pkg = current_menu.get("package")
        assert pkg is not None
        assert pkg["pricing_mode"] == "composition"
        assert pkg["veg_price_cents"] == 6499
        assert pkg["mixed_price_cents"] == 6999
        assert pkg["nonveg_price_cents"] == 7999
        assert pkg["pick_count"] == 5
        assert len(pkg["eligible_master_ids"]) == 10

    def test_package_enabled_alacarte_disabled(self, current_menu):
        assert current_menu["package_enabled"] is True
        assert current_menu["alacarte_enabled"] is False

    def test_ten_eligible_items(self, current_menu):
        # 10 dishes: 5 veg + 5 non-veg (including eggitarian counted as nv)
        assert len(current_menu["items"]) == 10
        veg, nv, egg = _split_items(current_menu)
        assert len(veg) == 5
        # Anda Tadka is eggitarian, others in non-veg category are non-vegetarian
        assert len(nv) + len(egg) == 5

    def test_complimentary_items(self, current_menu):
        comp = current_menu.get("complimentary_items") or []
        names = sorted([c["name"] for c in comp])
        assert names == ["Dal of the Week", "Gur er Payesh"], f"got {names}"
        for c in comp:
            assert c.get("image_url"), f"complimentary {c['name']} missing image"


# ---------- 2. /menu/anytime ----------
class TestMenuAnytime:
    def test_anytime_seven_items(self, client):
        r = client.get(f"{API}/menu/anytime")
        assert r.status_code == 200
        arr = r.json()
        assert isinstance(arr, list)
        assert len(arr) == 7, f"expected 7 anytime items, got {len(arr)}"
        expected = {"Roti", "Mughlai Paratha", "Chicken Biryani", "Mutton Biryani",
                    "Egg Roll", "Chicken Roll", "Mutton Roll"}
        got = {x["name"] for x in arr}
        assert got == expected, f"missing/extra items: got={got}"
        for it in arr:
            assert it.get("image_url"), f"{it['name']} missing image_url"
            assert isinstance(it.get("price_cents"), int) and it["price_cents"] > 0


# ---------- 3. Composition pricing on /orders/quote ----------
class TestCompositionPricing:
    def test_five_veg_price_6499(self, client, guest_hdr, current_menu):
        veg, _, _ = _split_items(current_menu)
        picks = [it["item_id"] for it in veg[:5]]
        assert len(picks) == 5
        body = {
            "items": [{"kind": "weekly_package", "ref_id": current_menu["menu_id"],
                       "quantity": 1, "package_selections": picks}],
            "address": _addr(), "slot": _slot(),
        }
        r = client.post(f"{API}/orders/quote", json=body, headers=guest_hdr)
        assert r.status_code == 200, r.text
        q = r.json()
        assert q["subtotal_cents"] == 6499, q
        snap = q["items_snapshot"][0]
        assert snap["line_total_cents"] == 6499
        assert snap["kind"] == "weekly_package"

    def test_mixed_veg_and_nonveg_price_6999(self, client, guest_hdr, current_menu):
        veg, nv, _ = _split_items(current_menu)
        picks = [it["item_id"] for it in veg[:3]] + [it["item_id"] for it in nv[:2]]
        assert len(picks) == 5
        body = {
            "items": [{"kind": "weekly_package", "ref_id": current_menu["menu_id"],
                       "quantity": 1, "package_selections": picks}],
            "address": _addr(), "slot": _slot(),
        }
        r = client.post(f"{API}/orders/quote", json=body, headers=guest_hdr)
        assert r.status_code == 200, r.text
        assert r.json()["subtotal_cents"] == 6999

    def test_five_nonveg_price_7999(self, client, guest_hdr, current_menu):
        _, nv, egg = _split_items(current_menu)
        pool = nv + egg
        picks = [it["item_id"] for it in pool[:5]]
        assert len(picks) == 5
        body = {
            "items": [{"kind": "weekly_package", "ref_id": current_menu["menu_id"],
                       "quantity": 1, "package_selections": picks}],
            "address": _addr(), "slot": _slot(),
        }
        r = client.post(f"{API}/orders/quote", json=body, headers=guest_hdr)
        assert r.status_code == 200, r.text
        assert r.json()["subtotal_cents"] == 7999

    def test_egg_counts_as_nonveg_mixed(self, client, guest_hdr, current_menu):
        veg, _, egg = _split_items(current_menu)
        if not egg:
            pytest.skip("no eggitarian item in current menu")
        picks = [it["item_id"] for it in veg[:4]] + [egg[0]["item_id"]]
        assert len(picks) == 5
        body = {
            "items": [{"kind": "weekly_package", "ref_id": current_menu["menu_id"],
                       "quantity": 1, "package_selections": picks}],
            "address": _addr(), "slot": _slot(),
        }
        r = client.post(f"{API}/orders/quote", json=body, headers=guest_hdr)
        assert r.status_code == 200, r.text
        # 4 veg + 1 egg => mixed since egg counts as non-veg
        assert r.json()["subtotal_cents"] == 6999, r.json()

    def test_four_picks_rejected(self, client, guest_hdr, current_menu):
        veg, _, _ = _split_items(current_menu)
        picks = [it["item_id"] for it in veg[:4]]
        body = {
            "items": [{"kind": "weekly_package", "ref_id": current_menu["menu_id"],
                       "quantity": 1, "package_selections": picks}],
            "address": _addr(), "slot": _slot(),
        }
        r = client.post(f"{API}/orders/quote", json=body, headers=guest_hdr)
        assert r.status_code == 400, r.text

    def test_six_picks_rejected(self, client, guest_hdr, current_menu):
        picks = [it["item_id"] for it in current_menu["items"][:6]]
        body = {
            "items": [{"kind": "weekly_package", "ref_id": current_menu["menu_id"],
                       "quantity": 1, "package_selections": picks}],
            "address": _addr(), "slot": _slot(),
        }
        r = client.post(f"{API}/orders/quote", json=body, headers=guest_hdr)
        assert r.status_code == 400, r.text


# ---------- 4. COD order placement ----------
class TestOrderPlacement:
    def test_place_cod_weekly_package(self, client, guest_hdr, current_menu):
        veg, nv, _ = _split_items(current_menu)
        picks = [it["item_id"] for it in veg[:3]] + [it["item_id"] for it in nv[:2]]
        body = {
            "items": [{"kind": "weekly_package", "ref_id": current_menu["menu_id"],
                       "quantity": 1, "package_selections": picks}],
            "address": _addr(), "slot": _slot(),
            "phone": "4165551234", "payment_method": "cod",
            "customer_name": "TEST Guest",
        }
        r = client.post(f"{API}/orders", json=body, headers=guest_hdr)
        assert r.status_code == 200, r.text
        o = r.json()
        assert o["subtotal_cents"] == 6999, o
        snap = o["items_snapshot"][0]
        assert snap["line_total_cents"] == 6999
        assert snap["weekly_menu_id"] == current_menu["menu_id"]
        assert len(snap.get("package_selection_ids", [])) == 5


# ---------- 5. Admin composition-price editing ----------
class TestAdminCompositionPrices:
    def test_admin_can_update_three_prices(self, client, admin_hdr, current_menu):
        ws = current_menu["week_start"]
        original_pkg = current_menu["package"]
        # Modify only the three composition prices; preserve everything else.
        new_pkg = {**original_pkg,
                   "veg_price_cents": 5999,
                   "mixed_price_cents": 6499,
                   "nonveg_price_cents": 7499,
                   "pricing_mode": "composition"}
        # eligible_master_ids may be required — pass through
        r = client.post(f"{API}/admin/menus/{ws}/settings",
                        json={"package": new_pkg, "package_enabled": True},
                        headers=admin_hdr)
        assert r.status_code == 200, r.text
        # verify persistence
        m2 = client.get(f"{API}/menu/current").json()
        p2 = m2["package"]
        assert p2["veg_price_cents"] == 5999
        assert p2["mixed_price_cents"] == 6499
        assert p2["nonveg_price_cents"] == 7499
        assert p2["pricing_mode"] == "composition"

        # RESTORE original values (critical for downstream tests / clean state)
        restore = {**original_pkg}
        rr = client.post(f"{API}/admin/menus/{ws}/settings",
                         json={"package": restore, "package_enabled": True},
                         headers=admin_hdr)
        assert rr.status_code == 200, rr.text
        m3 = client.get(f"{API}/menu/current").json()
        assert m3["package"]["veg_price_cents"] == 6499
        assert m3["package"]["mixed_price_cents"] == 6999
        assert m3["package"]["nonveg_price_cents"] == 7999
