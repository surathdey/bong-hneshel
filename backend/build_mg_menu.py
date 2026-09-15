"""
build_mg_menu.py — one-shot builder for Mustard Garden's master menu.

Reads the dish list extracted from the 5 weekly-meal-plan posters, uses the
existing AI enrichment pipeline (menu_ai.enrich_item → GPT text + Gemini Nano
Banana food image) and upserts each dish into `master_menu`.

- Price: 1599 cents ($15.99) for every item (owner will tune later).
- category / veg_type are taken from the poster grouping (authoritative),
  descriptions + spice + allergens + image come from the AI.
- Idempotent: upsert keyed on `name`.
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

import menu_ai  # uses EMERGENT_LLM_KEY from .env

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
PRICE_CENTS = 1599

# (name, category, veg_type)  — category ∈ menu_ai.CATEGORIES
DISHES = [
    # ---------------- VEG DISHES ----------------
    ("Shorshey Bhindi", "main-veg", "vegetarian"),
    ("Soyabean Aloo Dalna", "main-veg", "vegetarian"),
    ("Lau er Daal", "main-veg", "vegetarian"),
    ("Beet Gajorer Tarkari", "main-veg", "vegetarian"),
    ("Jhingey Aloo Posto", "main-veg", "vegetarian"),
    ("Dhokar Dalna", "main-veg", "vegetarian"),
    ("Navratan Korma", "main-veg", "vegetarian"),
    ("Paneer Aloo Dalna", "main-veg", "vegetarian"),
    ("Posto diye Bhindi Aloo Bhaja", "main-veg", "vegetarian"),
    ("Sabji diye Laal Saag Ghonto", "main-veg", "vegetarian"),
    ("Kanchkola Kofta", "main-veg", "vegetarian"),
    ("Potol Aloo Posto", "main-veg", "vegetarian"),
    ("Panchmishali Tarkari", "main-veg", "vegetarian"),
    ("Palong Paneer", "main-veg", "vegetarian"),
    ("Mushroom Shorshey (Besara)", "main-veg", "vegetarian"),
    ("Niramis Badhakopi", "main-veg", "vegetarian"),
    ("Fulkopi Aloo Kosha", "main-veg", "vegetarian"),
    ("Soyabean Pasanda", "main-veg", "vegetarian"),
    ("Bori diye Laue Ghonto", "main-veg", "vegetarian"),
    ("Echor Aloo Dalna", "main-veg", "vegetarian"),
    ("Masala Vendi", "main-veg", "vegetarian"),
    ("Palong Ghonto", "main-veg", "vegetarian"),
    ("Motor Paneer", "main-veg", "vegetarian"),
    ("Aloo Korolar Jhal", "main-veg", "vegetarian"),

    # ---------------- NON-VEG: EGG ----------------
    ("Anda Tadka", "main-non-veg", "eggitarian"),
    ("Dimer Jhol", "main-non-veg", "eggitarian"),
    ("Dim Aloo Dalna", "main-non-veg", "eggitarian"),

    # ---------------- NON-VEG: CHICKEN ----------------
    ("Morich Chicken", "main-non-veg", "non-vegetarian"),
    ("Murgir Laal Jhol", "main-non-veg", "non-vegetarian"),
    ("Chicken Dak Bunglow", "main-non-veg", "non-vegetarian"),
    ("Lebu Lonka Chicken", "main-non-veg", "non-vegetarian"),
    ("Chicken Aloo Jhol", "main-non-veg", "non-vegetarian"),

    # ---------------- NON-VEG: FISH / PRAWN ----------------
    ("Pui Chingri Ghonto", "main-non-veg", "non-vegetarian"),
    ("Rui Aloo Jhol", "main-non-veg", "non-vegetarian"),
    ("Potol Aloo diye Rui Mach", "main-non-veg", "non-vegetarian"),
    ("Lau Chingri", "main-non-veg", "non-vegetarian"),
    ("Rui Mach Gobi diye Jhol", "main-non-veg", "non-vegetarian"),
    ("Data diye Chingri Mach", "main-non-veg", "non-vegetarian"),
    ("Aloo Bori diye Pabda", "main-non-veg", "non-vegetarian"),
    ("Oll Chingri", "main-non-veg", "non-vegetarian"),
    ("Doi Rui", "main-non-veg", "non-vegetarian"),

    # ---------------- NON-VEG: MUTTON ----------------
    ("Mutton Resala", "main-non-veg", "non-vegetarian"),
    ("Mutton Dak Bunglow", "main-non-veg", "non-vegetarian"),
    ("Gondhoraj Mutton", "main-non-veg", "non-vegetarian"),
    ("Mutton er Patla Alu diye Jhol", "main-non-veg", "non-vegetarian"),
    ("Mutton Kosa", "main-non-veg", "non-vegetarian"),

    # ---------------- COMPLIMENTARY ----------------
    ("Gur er Payesh", "dessert", "vegetarian"),
    ("Jhuri Aloo Bhaja", "side", "vegetarian"),
    ("Dal of the Week", "side", "vegetarian"),
    ("Chutney of the Week", "side", "vegetarian"),
    ("Rice", "rice", "vegetarian"),

    # ---------------- ADD-ONS ----------------
    ("Roti", "bread", "vegetarian"),
    ("Mughlai Paratha", "bread", "eggitarian"),
    ("Kolkata Rolls", "starter", "eggitarian"),
    ("Biryani", "rice", "non-vegetarian"),
]


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    sem = asyncio.Semaphore(5)
    results = {"ok": 0, "no_image": 0, "err": 0}

    async def build_one(idx, name, category, veg_type):
        async with sem:
            try:
                ai = await menu_ai.enrich_item(name, PRICE_CENTS, want_image=True)
            except Exception as e:
                print(f"[ERR] {name}: {e}")
                results["err"] += 1
                from menu_ai import _fallback_text
                ai = {**_fallback_text(name), "image_url": ""}

            image_url = ai.get("image_url") or ""
            # one retry for the image if it came back empty
            if not image_url:
                try:
                    image_url = await menu_ai.enrich_image(
                        name, ai.get("short_description", ""), "bengali"
                    )
                except Exception:
                    image_url = ""
            if not image_url:
                results["no_image"] += 1

            doc = {
                "item_id": f"mi_{uuid.uuid4().hex[:10]}",
                "name": name,
                "short_description": ai.get("short_description", ""),
                "full_description": ai.get("full_description", ""),
                "category": category,                 # poster-authoritative
                "cuisine": ai.get("cuisine", "bengali"),
                "default_price_cents": PRICE_CENTS,
                "cost_price_cents": 0,
                "image_url": image_url,
                "extra_images": [],
                "veg_type": veg_type,                 # poster-authoritative
                "spice_level": ai.get("spice_level", "medium"),
                "allergens": ai.get("allergens", []),
                "is_active": True,
                "prep_notes": "",
                "kitchen_notes": "",
                "display_order": idx,
                "updated_at": datetime.now(timezone.utc),
            }
            existing = await db.master_menu.find_one({"name": name}, {"item_id": 1})
            if existing:
                doc["item_id"] = existing["item_id"]
                doc.pop("item_id", None)
                await db.master_menu.update_one({"name": name}, {"$set": doc})
            else:
                doc["created_at"] = datetime.now(timezone.utc)
                await db.master_menu.update_one(
                    {"name": name}, {"$set": doc}, upsert=True
                )
            results["ok"] += 1
            print(f"[{results['ok']:2d}/{len(DISHES)}] {name}  img={'yes' if image_url else 'NO'}")

    await asyncio.gather(
        *[build_one(i, n, c, v) for i, (n, c, v) in enumerate(DISHES)]
    )
    total = await db.master_menu.count_documents({})
    print(f"\nDONE. ok={results['ok']} no_image={results['no_image']} err={results['err']} | master_menu total={total}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
