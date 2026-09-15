"""build_weekly.py — mark all-time items, add roll/biryani variants, and
publish the 24-Aug weekly meal plan with composition-based pricing."""
import asyncio, os, uuid
from datetime import datetime, timezone, date, timedelta
from dotenv import load_dotenv
load_dotenv()
from motor.motor_asyncio import AsyncIOMotorClient
import menu_ai

db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
PRICE = 1599

# New all-time-available items to add (category, veg_type)
NEW_ANYTIME = [
    ("Chicken Biryani", "rice", "non-vegetarian"),
    ("Mutton Biryani", "rice", "non-vegetarian"),
    ("Egg Roll", "starter", "eggitarian"),
    ("Chicken Roll", "starter", "non-vegetarian"),
    ("Mutton Roll", "starter", "non-vegetarian"),
]
# Existing items to flag as always-available
MARK_ANYTIME = ["Roti", "Mughlai Paratha"]

# 24-Aug weekly plan
WEEK_VEG = ["Masala Vendi", "Dhokar Dalna", "Palong Ghonto", "Motor Paneer", "Aloo Korolar Jhal"]
WEEK_NONVEG = ["Anda Tadka", "Lau Chingri", "Chicken Aloo Jhol", "Doi Rui", "Mutton Kosa"]
COMPLIMENTARY = ["Gur er Payesh", "Dal of the Week"]


async def gen_img(name, desc, tries=5):
    delay = 4
    for _ in range(tries):
        u = await menu_ai.enrich_image(name, desc, "bengali")
        if u:
            return u
        await asyncio.sleep(delay); delay = min(delay*2, 30)
    return ""


async def get_id(name):
    d = await db.master_menu.find_one({"name": name}, {"_id": 0, "item_id": 1})
    return d["item_id"] if d else None


async def main():
    # 1) add new anytime items (with AI text + image), sequential
    for i, (name, cat, veg) in enumerate(NEW_ANYTIME):
        exists = await db.master_menu.find_one({"name": name}, {"item_id": 1})
        txt = await menu_ai.enrich_text(name, PRICE)
        img = await gen_img(name, txt.get("short_description", ""))
        doc = {
            "name": name, "short_description": txt["short_description"],
            "full_description": txt["full_description"], "category": cat,
            "cuisine": txt.get("cuisine", "bengali"), "default_price_cents": PRICE,
            "cost_price_cents": 0, "image_url": img, "extra_images": [],
            "veg_type": veg, "spice_level": txt.get("spice_level", "medium"),
            "allergens": txt.get("allergens", []), "is_active": True,
            "always_available": True, "prep_notes": "", "kitchen_notes": "",
            "display_order": 900 + i, "updated_at": datetime.now(timezone.utc),
        }
        if exists:
            await db.master_menu.update_one({"name": name}, {"$set": doc})
        else:
            doc["item_id"] = f"mi_{uuid.uuid4().hex[:10]}"
            doc["created_at"] = datetime.now(timezone.utc)
            await db.master_menu.update_one({"name": name}, {"$set": doc}, upsert=True)
        print("anytime item:", name, "img=", "yes" if img else "NO")

    # 2) flag existing items as always-available
    r = await db.master_menu.update_many({"name": {"$in": MARK_ANYTIME}}, {"$set": {"always_available": True}})
    print("flagged existing anytime:", r.modified_count)

    # 3) build weekly menu lines from master items
    all_names = WEEK_VEG + WEEK_NONVEG
    lines = []
    for order, name in enumerate(all_names):
        mid = await get_id(name)
        if not mid:
            print("!! missing master item:", name); continue
        lines.append({
            "line_id": f"wl_{uuid.uuid4().hex[:10]}", "master_item_id": mid,
            "price_override_cents": None, "availability": "available",
            "stock_limit": None, "stock_used": 0, "is_featured": False,
            "display_order": order,
        })
    eligible = [l["master_item_id"] for l in lines]
    comp_ids = [await get_id(n) for n in COMPLIMENTARY]
    comp_ids = [c for c in comp_ids if c]

    package = {
        "package_id": f"wpkg_{uuid.uuid4().hex[:10]}",
        "name": "Weekly Meal Plan",
        "description": "Pick any 5 dishes. Price adjusts to your veg / non-veg mix.",
        "price_cents": 0,
        "pick_count": 5,
        "eligible_master_ids": eligible,
        "item_surcharges_cents": {},
        "image_url": "",
        "pricing_mode": "composition",
        "veg_price_cents": 6499,
        "mixed_price_cents": 6999,
        "nonveg_price_cents": 7999,
        "complimentary_master_ids": comp_ids,
    }

    today = datetime.now(timezone.utc).date()
    week_start = (today - timedelta(days=(today.weekday()+1) % 7)).isoformat()
    week_end = (date.fromisoformat(week_start) + timedelta(days=6)).isoformat()

    menu = {
        "menu_id": f"menu_{uuid.uuid4().hex[:10]}",
        "week_start": week_start, "week_end": week_end,
        "title": "Weekly Meal Plan — 24th Aug",
        "description": "Exotic flavors of India, delivered fresh.",
        "banner_image_url": "",
        "items": [], "lines": lines,
        "published": True, "status": "published",
        "alacarte_enabled": False, "package_enabled": True, "package": package,
        "created_at": datetime.now(timezone.utc),
    }
    await db.weekly_menus.update_one({"week_start": week_start}, {"$set": menu}, upsert=True)
    print(f"\nweekly menu published: week_start={week_start} lines={len(lines)} eligible={len(eligible)} complimentary={len(comp_ids)}")
    print("pricing: veg=6499 mixed=6999 nonveg=7999 pick=5")


if __name__ == "__main__":
    asyncio.run(main())
