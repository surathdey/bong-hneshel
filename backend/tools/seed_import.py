"""
================================================================
 Curry-Co-Template · Seed-Pack Importer
================================================================

Reads a `seed_pack.json` produced by `seed_export.py` and hydrates
the CURRENT tenant DB with its content. Idempotent — running it
twice is safe (uses upsert on the primary key of each collection).

USAGE
    cd backend
    python3 -m tools.seed_import /path/to/seed_pack.json
    python3 -m tools.seed_import seed_pack.json --wipe      # drop first
    python3 -m tools.seed_import seed_pack.json --only master_menu weekly_menus

SAFETY
    • Refuses to run if MONGO_URL points at a DB whose brand.json `key`
      matches the seed pack's `_meta.source_brand` (prevents accidental
      self-import that would nuke your own live catalog).
    • `--wipe` requires explicit --i-know for destructive runs.

WHAT GETS INSERTED
    Same collections as the export. Every doc is stamped with a fresh
    `created_at` / `updated_at` on the target side.
================================================================
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv


# The natural key of each collection. Import upserts on this field.
PRIMARY_KEY: Dict[str, str] = {
    "master_menu":        "item_id",
    "weekly_menus":       "menu_id",   # falls back to week_start when menu_id absent
    "catering_packages":  "package_id",
    "coupons":            "code",
    "delivery_zones":     "zone_id",
    "business_settings":  "key",       # always "default"
}

# Fallback keys when the primary is missing on a legacy row.
FALLBACK_KEY: Dict[str, str] = {
    "weekly_menus": "week_start",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read_brand_key() -> str:
    try:
        brand_path = Path(__file__).resolve().parent.parent.parent / "brand.json"
        return json.loads(brand_path.read_text("utf-8")).get("key", "unknown")
    except Exception:
        return "unknown"


async def _upsert(db, coll: str, docs: List[Dict[str, Any]]) -> int:
    inserted = 0
    pk = PRIMARY_KEY.get(coll)
    fallback = FALLBACK_KEY.get(coll)
    for doc in docs:
        doc["created_at"] = doc.get("created_at") or _now()
        doc["updated_at"] = _now()
        key_field = pk if pk and doc.get(pk) else fallback
        if not key_field or not doc.get(key_field):
            # No usable key → just insert (accept duplicates).
            await db[coll].insert_one(doc)
        else:
            await db[coll].update_one(
                {key_field: doc[key_field]}, {"$set": doc}, upsert=True
            )
        inserted += 1
    return inserted


async def _run(seed_path: Path, wipe: bool, i_know: bool, only: set[str]) -> None:
    load_dotenv()
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "curryco")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    pack = json.loads(seed_path.read_text("utf-8"))
    meta = pack.get("_meta", {})

    # Self-import guard.
    my_brand = _read_brand_key()
    if meta.get("source_brand") and meta["source_brand"] == my_brand:
        print(f"⚠ Refusing to import: source_brand='{meta['source_brand']}' matches this tenant's brand.")
        print(f"  If you REALLY want to overwrite your own catalog, edit brand.json first.")
        sys.exit(2)

    print(f"Importing seed pack (source: {meta.get('source_brand','?')}, generated {meta.get('generated_at','?')})")
    print(f"Target DB: {db_name}\n")

    if wipe and not i_know:
        print("⛔ --wipe requires --i-know to confirm destructive intent.")
        sys.exit(3)

    total = 0
    for coll_meta in meta.get("collections", []):
        coll = coll_meta["name"]
        if only and coll not in only:
            continue
        rows = pack.get(coll, [])
        if wipe:
            deleted = (await db[coll].delete_many({})).deleted_count
            print(f"  · {coll:<20s} wiped {deleted} existing rows")
        n = await _upsert(db, coll, rows)
        total += n
        print(f"  · {coll:<20s} upserted {n:>4d} rows")

    print(f"\n✔ Imported {total} rows into `{db_name}` — target DB is ready to serve.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a tenant seed pack")
    parser.add_argument("seed", type=Path, help="Path to seed_pack.json")
    parser.add_argument("--wipe", action="store_true",
                        help="Delete existing rows in each target collection before upserting")
    parser.add_argument("--i-know", action="store_true",
                        help="Required alongside --wipe to confirm you understand the destruction")
    parser.add_argument("--only", nargs="*", default=[],
                        help="Restrict import to these collection names")
    args = parser.parse_args()
    asyncio.run(_run(args.seed, args.wipe, args.i_know, set(args.only)))


if __name__ == "__main__":
    main()
