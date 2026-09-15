"""
Seed 8 emergency orders + assign to driver "Surath Dey".

Runs against whatever MongoDB the backend is currently pointed at
(so on Emergent's production deployment this hits the live prod DB).

For each customer:
  1. upsert user record (found by phone; else create)
  2. create address doc with GTA approximate lat/lng
  3. create weekly-package order (picks the first `pick_count` eligible
     items from this week's menu), status = "confirmed" → tracked as
     "preparing" → "out_for_delivery", assigned to Surath Dey.
  4. seed loyalty points = 0

Also idempotent: rerunning updates rather than duplicates.

Usage:
    cd /app/backend && python -m tools.seed_emergency_orders
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext

load_dotenv()

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

DRIVER_NAME = "Surath Dey"
DRIVER_EMAIL = "surath.dey@curryandco.local"
DRIVER_PHONE = "+16475551212"
DRIVER_PASSWORD = "surath@delivery2026"  # printed at the end so ops can log in

# --- Approx GTA coordinates by city, close enough for the driver's map -----
CITY_LATLNG = {
    "brampton":     (43.7315, -79.7624),
    "mississauga":  (43.5890, -79.6441),
    "milton":       (43.5183, -79.8774),
    "toronto":      (43.6532, -79.3832),
    "markham":      (43.8561, -79.3370),
}


def guess_latlng(city: str) -> tuple[float, float]:
    key = (city or "").strip().lower()
    return CITY_LATLNG.get(key, (43.65, -79.4))  # fallback: central GTA


def parse_address(full: str) -> Dict[str, str]:
    """Best-effort parse of 'line1, city, postal_code' → structured pieces."""
    parts = [p.strip() for p in (full or "").split(",")]
    line1 = parts[0] if parts else full
    city = parts[1] if len(parts) > 1 else "Mississauga"
    postal_raw = parts[2] if len(parts) > 2 else ""
    # If the postal contains ON/state code, strip it — e.g. "ON L5R 4B1".
    tokens = postal_raw.split()
    postal = " ".join(t for t in tokens if not t.upper() in ("ON", "ONTARIO"))
    return {"line1": line1, "city": city.title(), "postal_code": postal.upper()}


# --- 8 customers from the uploaded spreadsheet ------------------------------
CUSTOMERS = [
    {"name": "Dhruba Ghosh",     "phone": "+16472803228",  "addr": "1003-2 Silvermaple Court, Brampton, L6T4R1"},
    {"name": "Madhusmita Dutta", "phone": "",              "addr": "2330 Edenhurst Dr, Mississauga, L5A 2K9"},
    {"name": "Sreya Roy",        "phone": "+15199330890",  "addr": "1046 chateau court, Mississauga, L5H4J8"},
    {"name": "Ruma Nandi",       "phone": "+19057499435",  "addr": "355 Cochrane Terrace, Milton, L9T 8C1"},
    {"name": "Baishaki",         "phone": "+16479092890",  "addr": "1398 Grist Mill Court, Mississauga, L5V1S5"},
    {"name": "Amal Sen",         "phone": "+16473946369",  "addr": "25 Kingsbridge Garden Cir, Mississauga, ON L5R 4B1"},
    {"name": "Pooja",            "phone": "+14379900202",  "addr": "2054 Teeside Ct, Mississauga, L5M3E5"},
    {"name": "Rajib",            "phone": "+16472890774",  "addr": "6810 Meadowale Towncenter Circle, Mississauga, L5N7T5"},
]


def sunday_of(d: date) -> date:
    days_since_sun = (d.weekday() + 1) % 7  # Sun→0, Mon→1, ..., Sat→6
    return d - timedelta(days=days_since_sun)


def next_delivery_day(today: date, delivery_days: List[int]) -> date:
    """Return the closest upcoming delivery day (0=Sun...6=Sat)."""
    if not delivery_days:
        return today + timedelta(days=1)
    # weekday(): Mon=0..Sun=6 → convert to our Sun=0 numbering
    def our_dow(d: date) -> int:
        return (d.weekday() + 1) % 7
    for i in range(0, 8):
        cand = today + timedelta(days=i)
        if our_dow(cand) in delivery_days:
            return cand
    return today + timedelta(days=1)


async def upsert_driver(db) -> Dict:
    existing = await db.delivery_partners.find_one({"name": DRIVER_NAME}, {"_id": 0})
    if existing:
        # Ensure active + refresh password so the credentials in this file work.
        await db.delivery_partners.update_one(
            {"partner_id": existing["partner_id"]},
            {"$set": {
                "is_active": True,
                "password_hash": _pwd.hash(DRIVER_PASSWORD),
                "phone": DRIVER_PHONE,
                "email": DRIVER_EMAIL,
                "updated_at": datetime.now(timezone.utc),
                "current_lat": 43.5890,
                "current_lng": -79.6441,
                "current_location_updated_at": datetime.now(timezone.utc),
            }},
        )
        return await db.delivery_partners.find_one({"partner_id": existing["partner_id"]}, {"_id": 0})

    partner_id = f"dp_{uuid.uuid4().hex[:10]}"
    doc = {
        "partner_id": partner_id,
        "name": DRIVER_NAME,
        "email": DRIVER_EMAIL,
        "phone": DRIVER_PHONE,
        "vehicle": "car",
        "password_hash": _pwd.hash(DRIVER_PASSWORD),
        "is_active": True,
        "current_lat": 43.5890,   # Mississauga centroid, so the map has a starting pin
        "current_lng": -79.6441,
        "current_location_updated_at": datetime.now(timezone.utc),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    await db.delivery_partners.insert_one(doc)
    return doc


async def upsert_user(db, name: str, phone: str, address: Dict) -> Dict:
    """Find by phone (if provided) else by name — never create duplicates."""
    query: Dict = {}
    if phone:
        query["phone"] = phone
    else:
        # For rows with no phone (Madhusmita), we still want idempotency by name.
        query["name"] = name

    existing = await db.users.find_one(query, {"_id": 0})
    if existing:
        await db.users.update_one(
            {"user_id": existing["user_id"]},
            {"$set": {"name": name, "phone": phone or existing.get("phone", ""),
                      "default_address": address,
                      "updated_at": datetime.now(timezone.utc)}},
        )
        return await db.users.find_one({"user_id": existing["user_id"]}, {"_id": 0})

    user_id = f"user_{uuid.uuid4().hex[:12]}"
    # Synthesize a placeholder email so store-review flows don't blow up.
    safe = "".join(c.lower() if c.isalnum() else "" for c in name) or "customer"
    doc = {
        "user_id": user_id,
        "email": f"{safe}.{user_id[-6:]}@guest.curryandco.local",
        "name": name,
        "phone": phone,
        "picture": None,
        "loyalty_points": 0,
        "created_at": datetime.now(timezone.utc),
        "role": "customer",
        "default_address": address,
    }
    await db.users.insert_one(doc)
    return doc


async def get_current_week_menu(db) -> Optional[Dict]:
    today = datetime.now(timezone.utc).date()
    ws = sunday_of(today).isoformat()
    doc = await db.weekly_menus.find_one({"week_start": ws}, {"_id": 0})
    if not doc:
        raise RuntimeError(f"No weekly menu for week_start={ws}. Publish this week's menu first.")
    if not doc.get("package_enabled") or not doc.get("package"):
        raise RuntimeError(
            f"This week's menu ({ws}, id={doc.get('menu_id')}) does not have a weekly-combo package enabled. "
            f"Enable the combo in Admin → Weekly Menu → Package before running this seeder."
        )
    return doc


async def pick_combo_selections(db, wm: Dict) -> List[str]:
    """Return a list of `pick_count` master_item_ids from the eligible pool."""
    pkg = wm["package"]
    pick_count = int(pkg.get("pick_count") or 0)
    line_master_ids = [ln.get("master_item_id") for ln in (wm.get("lines") or []) if ln.get("master_item_id")]
    eligible = pkg.get("eligible_master_ids") or line_master_ids
    if not eligible:
        raise RuntimeError("Weekly package has no eligible items to pick from.")
    if pick_count <= 0:
        raise RuntimeError("Weekly package pick_count is zero or missing.")
    # Simple deterministic choice — first N of eligible pool. Repeat if pool is small.
    picks: List[str] = []
    while len(picks) < pick_count:
        for mid in eligible:
            picks.append(mid)
            if len(picks) >= pick_count:
                break
    return picks[:pick_count]


async def create_order(db, user: Dict, wm: Dict, picks: List[str], driver: Dict, settings: Dict) -> Dict:
    """Create a confirmed weekly-package order assigned to `driver`.

    Idempotency: if an order already exists for this user + this week + this
    weekly menu_id + this driver, we skip creation.
    """
    existing = await db.orders.find_one({
        "user_id": user["user_id"],
        "items_snapshot.kind": "weekly_package",
        "items_snapshot.weekly_menu_id": wm["menu_id"],
        "delivery_partner_id": driver["partner_id"],
    }, {"_id": 0})
    if existing:
        return {"order": existing, "created": False}

    pkg = wm["package"]

    # Resolve names for display
    unique = list(dict.fromkeys(picks))
    names_map: Dict[str, str] = {}
    async for m in db.master_menu.find({"item_id": {"$in": unique}}, {"_id": 0, "item_id": 1, "name": 1}):
        names_map[m["item_id"]] = m["name"]

    from collections import Counter
    counts = Counter(picks)
    display_names = [f"{names_map.get(mid, mid)} × {q}" if q > 1 else names_map.get(mid, mid)
                     for mid, q in counts.items()]

    price_cents = int(pkg.get("price_cents") or 0)
    surcharge_map = pkg.get("item_surcharges_cents") or {}
    surcharge_total = sum(int(surcharge_map.get(mid, 0) or 0) for mid in picks)
    unit_cents = price_cents + surcharge_total
    line_total = unit_cents

    item_snap = {
        "kind": "weekly_package",
        "ref_id": wm["menu_id"],
        "name": pkg.get("name") or "Weekly Combo",
        "unit_price_cents": unit_cents,
        "quantity": 1,
        "image_url": pkg.get("image_url") or wm.get("banner_image_url", ""),
        "line_total_cents": line_total,
        "package_selection_ids": picks,
        "package_selection_names": display_names,
        "package_pick_count": int(pkg.get("pick_count") or 0),
        "package_base_cents": price_cents,
        "package_surcharge_cents": surcharge_total,
        "weekly_menu_id": wm["menu_id"],
        "weekly_menu_week_start": wm.get("week_start"),
    }

    delivery_fee = int(settings.get("default_delivery_fee_cents") or 0)
    subtotal = line_total
    taxable = subtotal + delivery_fee
    # Emergency orders → skip tax to keep the totals clean for demo.
    tax_cents = 0
    total = taxable + tax_cents

    addr = user.get("default_address") or {}
    now = datetime.now(timezone.utc)

    today = now.date()
    dd_list = settings.get("delivery_days") or [5, 6]
    slot_date = next_delivery_day(today, dd_list).isoformat()
    slot_window = "saturday_morning" if 6 in dd_list else "friday_evening"

    lat, lng = guess_latlng(addr.get("city", ""))

    order_id = f"ord_{uuid.uuid4().hex[:10]}"
    order_doc = {
        "order_id": order_id,
        "user_id": user["user_id"],
        "items_snapshot": [item_snap],
        "address": {**addr, "lat": lat, "lng": lng, "instructions": ""},
        "slot": {"date": slot_date, "window": slot_window},
        "phone": user.get("phone", ""),
        "subtotal_cents": subtotal,
        "delivery_fee_cents": delivery_fee,
        "tax_cents": tax_cents,
        "tax_label": settings.get("tax_label", "HST"),
        "discount_cents": 0,
        "points_redeemed_cents": 0,
        "total_cents": total,
        "coupon_code": None,
        "special_instructions": "Emergency order (Aug 28 seed)",
        "payment_method": "cod",
        "status": "out_for_delivery",       # driver can see it and act on it
        "payment_status": "cod_pending",
        "stripe_session_id": None,
        "points_awarded": subtotal // 100,
        "refund_status": None,
        "created_at": now,
        "updated_at": now,
        "tracking_events": [
            {"status": "new",              "ts": now.isoformat(), "note": "Order created (emergency seed)"},
            {"status": "confirmed",        "ts": now.isoformat(), "note": "Order confirmed (Cash on Delivery)"},
            {"status": "preparing",        "ts": now.isoformat(), "note": "Kitchen preparing order"},
            {"status": "out_for_delivery", "ts": now.isoformat(), "note": f"Assigned to driver {driver['name']}"},
        ],
        # Delivery assignment
        "delivery_partner_id":       driver["partner_id"],
        "delivery_status":           "assigned",
        "delivery_partner_name":     driver.get("name"),
        "delivery_partner_phone":    driver.get("phone", ""),
        "delivery_partner_lat":      driver.get("current_lat"),
        "delivery_partner_lng":      driver.get("current_lng"),
        "delivery_partner_updated_at": now,
        "delivery_eta_seconds":      None,
        "delivery_eta_updated_at":   None,
        "delivery_route_order":      None,
    }
    await db.orders.insert_one(order_doc)
    return {"order": order_doc, "created": True}


async def main() -> int:
    print(f"Connecting to Mongo … db={DB_NAME}\n")
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    # 1. weekly menu / combo
    wm = await get_current_week_menu(db)
    print(f"✓ Using this-week menu {wm['menu_id']}  week_start={wm['week_start']}")
    print(f"  combo: {wm['package'].get('name')}  ${wm['package'].get('price_cents',0)/100:.2f}  pick_count={wm['package'].get('pick_count')}\n")

    # 2. driver
    driver = await upsert_driver(db)
    print(f"✓ Driver ready: {driver['name']}  partner_id={driver['partner_id']}  email={driver['email']}\n")

    # 3. settings for delivery-fee / delivery-days
    settings = await db.business_settings.find_one({"key": "default"}, {"_id": 0}) or {}

    # 4. seed each customer + order
    print("Seeding orders:")
    print("-" * 80)
    for row in CUSTOMERS:
        addr_parts = parse_address(row["addr"])
        addr = {**addr_parts, "province": "ON", "line2": ""}
        user = await upsert_user(db, row["name"], row["phone"], addr)

        picks = await pick_combo_selections(db, wm)
        result = await create_order(db, user, wm, picks, driver, settings)
        order = result["order"]
        flag = "NEW " if result["created"] else "SKIP"  # already existed
        print(f"  [{flag}]  {row['name']:20s} → order {order['order_id']}   total CA${order['total_cents']/100:>6.2f}   → {row['addr']}")
    print("-" * 80)

    # 5. summary
    total_orders = await db.orders.count_documents({
        "delivery_partner_id": driver["partner_id"],
        "delivery_status": {"$in": ["assigned", "picked_up", "on_the_way", "arrived"]},
    })
    print(f"\n✅ Driver {driver['name']} now has {total_orders} active order(s).")
    print(f"\n🔐 Delivery-partner login credentials for testing:")
    print(f"    URL:      /delivery-partner")
    print(f"    Email:    {DRIVER_EMAIL}")
    print(f"    Password: {DRIVER_PASSWORD}")
    print()

    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
