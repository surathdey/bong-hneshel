"""
fix_mg_images.py — regenerate missing menu images SEQUENTIALLY.

The Emergent key allows only 1 concurrent request, so we generate one image
at a time with retry/backoff on 429 rate-limit errors.
"""
import asyncio
import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()
import menu_ai

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


async def gen_with_retry(name, desc, cuisine, tries=5):
    delay = 4
    for attempt in range(1, tries + 1):
        url = await menu_ai.enrich_image(name, desc, cuisine)
        if url:
            return url
        await asyncio.sleep(delay)
        delay = min(delay * 2, 30)
    return ""


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    cur = db.master_menu.find(
        {"$or": [{"image_url": ""}, {"image_url": {"$exists": False}}]},
        {"_id": 0, "item_id": 1, "name": 1, "short_description": 1, "cuisine": 1},
    )
    todo = [d async for d in cur]
    print(f"missing images: {len(todo)}")

    done = 0
    still = 0
    for d in todo:
        url = await gen_with_retry(d["name"], d.get("short_description", ""), d.get("cuisine", "bengali"))
        if url:
            await db.master_menu.update_one({"item_id": d["item_id"]}, {"$set": {"image_url": url}})
            done += 1
            print(f"[{done}/{len(todo)}] OK   {d['name']} -> {url}")
        else:
            still += 1
            print(f"[--] FAIL {d['name']}")
        await asyncio.sleep(1.5)  # gentle pacing between requests

    total = await db.master_menu.count_documents({})
    withimg = await db.master_menu.count_documents({"image_url": {"$nin": ["", None]}})
    print(f"\nDONE. fixed={done} still_missing={still} | with_image={withimg}/{total}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
