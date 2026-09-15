"""
seed_bong_products.py — import Bong Hneshel products from bong_products.csv
into the `master_menu` collection.

For every product row (blank spacer rows are skipped):
  - price (dollars) -> default_price_cents (x100)
  - classification (category / cuisine / veg_type / spice_level / allergens) and
    a short_description come from menu_ai.enrich_text (GPT via Emergent key).
  - full_description: use the CSV description when present (HTML stripped),
    otherwise the LLM-generated full_description.
  - image_url: ALWAYS generated via menu_ai.enrich_image (Gemini Nano Banana),
    with retry/backoff (the Emergent key allows 1 concurrent request).

Idempotent: upsert keyed on `name`. Runs SEQUENTIALLY. Duplicate names in the
CSV are de-duped, preferring the row that carries a description.
"""
import asyncio
import csv
import html
import os
import re
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()
import menu_ai  # uses EMERGENT_LLM_KEY from .env

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
CSV_PATH = os.path.join(os.path.dirname(__file__), "bong_products.csv")

_TAG_RE = re.compile(r"<[^>]+>")


def clean_html(text: str) -> str:
    if not text:
        return ""
    t = _TAG_RE.sub(" ", text)          # strip HTML tags
    t = html.unescape(t)                # &nbsp; &amp; etc.
    t = re.sub(r"\s+", " ", t).strip()  # collapse whitespace
    return t


def parse_price_cents(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return int(round(float(raw) * 100))
    except ValueError:
        return None


def load_rows():
    """Return de-duped list of (name, description, price_cents) in CSV order."""
    by_name = {}
    order = []
    with open(CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("name") or "").strip()
            desc = clean_html(row.get("description") or "")
            price_cents = parse_price_cents(row.get("price"))
            if not name or price_cents is None:
                continue  # blank spacer row / no price
            if name in by_name:
                # keep the richer row (prefer one with a description)
                if not by_name[name]["description"] and desc:
                    by_name[name]["description"] = desc
                    by_name[name]["price_cents"] = price_cents
                continue
            by_name[name] = {"name": name, "description": desc, "price_cents": price_cents}
            order.append(name)
    return [by_name[n] for n in order]


async def gen_image_with_retry(name, desc, cuisine, tries=5):
    delay = 4
    for _ in range(tries):
        url = await menu_ai.enrich_image(name, desc, cuisine)
        if url:
            return url
        await asyncio.sleep(delay)
        delay = min(delay * 2, 30)
    return ""


async def enrich_text_with_retry(name, price_cents, tries=3):
    for attempt in range(tries):
        fields = await menu_ai.enrich_text(name, price_cents)
        # enrich_text never raises (returns fallback) — treat fallback as ok
        if fields:
            return fields
        await asyncio.sleep(3 * (attempt + 1))
    return menu_ai._fallback_text(name)


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    rows = load_rows()
    total = len(rows)
    print(f"[seed] DB={DB_NAME} products={total}", flush=True)

    ok = 0
    no_image = 0
    for idx, row in enumerate(rows):
        name = row["name"]
        price_cents = row["price_cents"]
        csv_desc = row["description"]

        # 1) classification + short description (+ LLM full desc as fallback)
        ai = await enrich_text_with_retry(name, price_cents)

        full_description = csv_desc if csv_desc else ai.get("full_description", "")
        short_description = ai.get("short_description", "")
        cuisine = ai.get("cuisine", "bengali")

        # 2) product image via Gemini Nano Banana
        image_url = await gen_image_with_retry(
            name, short_description or full_description[:120], cuisine
        )
        if not image_url:
            no_image += 1

        doc = {
            "name": name,
            "short_description": short_description,
            "full_description": full_description,
            "category": ai.get("category", "curry"),
            "cuisine": cuisine,
            "default_price_cents": price_cents,
            "cost_price_cents": 0,
            "image_url": image_url,
            "extra_images": [],
            "veg_type": ai.get("veg_type", "vegetarian"),
            "spice_level": ai.get("spice_level", "medium"),
            "allergens": ai.get("allergens", []),
            "is_active": True,
            "prep_notes": "",
            "kitchen_notes": "",
            "display_order": idx,
            "updated_at": datetime.now(timezone.utc),
            "source": "bong_products_csv",
        }

        existing = await db.master_menu.find_one({"name": name}, {"item_id": 1})
        if existing:
            await db.master_menu.update_one({"name": name}, {"$set": doc})
        else:
            doc["item_id"] = f"mi_{uuid.uuid4().hex[:10]}"
            doc["created_at"] = datetime.now(timezone.utc)
            await db.master_menu.update_one({"name": name}, {"$set": doc}, upsert=True)

        ok += 1
        print(f"[{ok:3d}/{total}] {name[:48]:48s} ${price_cents/100:>6.2f} "
              f"img={'yes' if image_url else 'NO '} veg={doc['veg_type'][:3]} cat={doc['category']}",
              flush=True)
        await asyncio.sleep(1.0)  # gentle pacing

    grand = await db.master_menu.count_documents({})
    withimg = await db.master_menu.count_documents({"image_url": {"$nin": ["", None]}})
    print(f"\n[seed] DONE ok={ok} no_image={no_image} | master_menu total={grand} with_image={withimg}",
          flush=True)
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
