"""fix_mg_text.py — regenerate fallback descriptions SEQUENTIALLY with retry."""
import asyncio, os
from dotenv import load_dotenv
load_dotenv()
from motor.motor_asyncio import AsyncIOMotorClient
import menu_ai

db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


async def enrich_retry(name, price, tries=6):
    delay = 4
    for _ in range(tries):
        r = await menu_ai.enrich_text(name, price)
        if not r["short_description"].startswith("House-style "):
            return r
        await asyncio.sleep(delay)
        delay = min(delay * 2, 30)
    return r  # give up → fallback


async def main():
    todo = [d async for d in db.master_menu.find(
        {"short_description": {"$regex": "^House-style "}},
        {"_id": 0, "item_id": 1, "name": 1, "default_price_cents": 1})]
    print("to fix:", len(todo))
    ok = fail = 0
    for i, d in enumerate(todo, 1):
        r = await enrich_retry(d["name"], d.get("default_price_cents", 1599))
        good = not r["short_description"].startswith("House-style ")
        await db.master_menu.update_one({"item_id": d["item_id"]}, {"$set": {
            "short_description": r["short_description"],
            "full_description": r["full_description"],
            "spice_level": r["spice_level"],
            "allergens": r["allergens"],
        }})
        ok += good; fail += (not good)
        print(f"[{i}/{len(todo)}] {'OK  ' if good else 'FB  '} {d['name']} :: {r['short_description'][:60]}")
        await asyncio.sleep(1.2)
    print(f"\nDONE. good={ok} stillfallback={fail}")


if __name__ == "__main__":
    asyncio.run(main())
