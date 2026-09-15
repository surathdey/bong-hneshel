"""
================================================================
 Curry-Co-Template · Seed-Pack Exporter
================================================================

Dumps the REUSABLE menu-side content of a live tenant DB into a
single portable JSON file (`seed_pack.json`) that can be imported
into any freshly-forked tenant (e.g. Jomidari) via `seed_import.py`.

WHAT IS EXPORTED (safe to share across brands):
    • master_menu        — the dish catalog
    • weekly_menus       — weekly rotations (published + drafts)
    • catering_packages  — per-guest packages
    • coupons            — promo codes
    • delivery_zones     — polygon-based delivery areas
    • business_settings  — currency / tax / delivery-day config
                           (brand-identifying fields like `business_name`,
                            `phone`, `kitchen_address`, `email` are BLANKED
                            because they belong in `brand.json`, not here)

WHAT IS *NOT* EXPORTED (tenant-private data — never leaves):
    users, orders, payment_transactions, delivery_partners,
    tracking events, exports, admins, business_settings.email,
    push tokens, address book entries.

USAGE
    cd backend
    python3 -m tools.seed_export                 # writes /app/seed_pack.json
    python3 -m tools.seed_export --out /tmp/x.json
    python3 -m tools.seed_export --skip coupons  # opt-out per collection

Then paste `seed_pack.json` into the target tenant's Emergent chat
and ask its agent to `python3 -m tools.seed_import seed_pack.json`.

The output is DETERMINISTIC (sorted keys) so diffs across dumps stay
readable in git.
================================================================
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv


# ---------------------------------------------------------------
# Config — which collections to dump and how to sanitize each row.
# ---------------------------------------------------------------
EXPORTABLE = [
    "master_menu",
    "weekly_menus",
    "catering_packages",
    "coupons",
    "delivery_zones",
    "business_settings",
]

# Fields we drop from EVERY collection — they're either brand-specific
# or auto-regenerated on the target side.
GLOBAL_SCRUB = {"_id", "created_at", "updated_at", "created_by", "updated_by"}

# Per-collection extras that should never cross tenants.
COLLECTION_SCRUB = {
    "business_settings": {
        "business_name",   # comes from brand.json now
        "email",           # comes from brand.json
        "phone",           # tenant-specific
        "kitchen_address", # tenant-specific
        "company_info",    # tenant-specific
        # payment_methods.* secrets — blanked below, not dropped, so
        # the target tenant still has the structural skeleton.
    },
    "coupons": {
        "usage_count",     # start fresh on the target
        "redeemed_by",     # tenant-private
    },
    "catering_packages": {
        # contact_email is tenant-specific — the fork's brand.json provides it.
        "contact_email",
    },
}


def _default_serializer(o: Any) -> Any:
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, bytes):
        return o.decode("utf-8", "ignore")
    return str(o)


def _sanitize(coll: str, doc: Dict[str, Any]) -> Dict[str, Any]:
    """Strip PII / brand-specific / auto-regen fields from a single doc."""
    for key in GLOBAL_SCRUB | COLLECTION_SCRUB.get(coll, set()):
        doc.pop(key, None)

    # business_settings needs extra care — blank secrets inside payment_methods.
    if coll == "business_settings" and isinstance(doc.get("payment_methods"), dict):
        for method, cfg in doc["payment_methods"].items():
            if not isinstance(cfg, dict):
                continue
            for secret_key in ("publishable_key", "secret_key", "client_id",
                                "client_secret", "webhook_secret", "email",
                                "instructions"):
                if secret_key in cfg:
                    cfg[secret_key] = ""

    return doc


async def _dump_collection(db, name: str) -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    async for raw in db[name].find({}):
        docs.append(_sanitize(name, raw))
    return docs


async def _run(out_path: Path, skip: set[str]) -> None:
    load_dotenv()
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "curryco")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    pack: Dict[str, Any] = {
        "_meta": {
            "schema_version": 1,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "source_db": db_name,
            # Read the brand key from brand.json if present (Phase 1 template).
            "source_brand": _read_brand_key(),
            "collections": [],
        }
    }

    for coll in EXPORTABLE:
        if coll in skip:
            continue
        docs = await _dump_collection(db, coll)
        pack[coll] = docs
        pack["_meta"]["collections"].append({"name": coll, "count": len(docs)})
        print(f"  · {coll:<20s} {len(docs):>4d} rows")

    out_path.write_text(
        json.dumps(pack, indent=2, sort_keys=True, default=_default_serializer),
        encoding="utf-8",
    )
    print(f"\n✔ Wrote {out_path.resolve()} ({out_path.stat().st_size:,} bytes)")
    print("  Paste it into the target tenant's chat and run `python3 -m tools.seed_import <path>`.")


def _read_brand_key() -> str:
    """Read `key` from repo-root brand.json — non-fatal if missing."""
    try:
        brand_path = Path(__file__).resolve().parent.parent.parent / "brand.json"
        return json.loads(brand_path.read_text("utf-8")).get("key", "unknown")
    except Exception:
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description="Export tenant seed pack")
    parser.add_argument("--out", type=Path, default=Path("/app/seed_pack.json"),
                        help="Output JSON file (default: /app/seed_pack.json)")
    parser.add_argument("--skip", nargs="*", default=[],
                        choices=EXPORTABLE,
                        help="Collections to skip")
    args = parser.parse_args()
    print(f"Exporting seed pack …\n")
    asyncio.run(_run(args.out, set(args.skip)))


if __name__ == "__main__":
    main()
