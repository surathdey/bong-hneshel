"""One-off: wipe customer/order/driver/delivery data in the PREVIEW db.
Keeps: menu (master_menu, weekly_menus, catering_packages), business_settings,
admins, and the reviewer customer account. Deletes everyone else + all coupons.
"""
import asyncio, os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
KEEP_REVIEWER = "reviewer@bong-hneshel.ca"


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    # Full wipes
    for coll in [
        "orders", "payment_transactions", "loyalty_ledger",
        "delivery_partners", "delivery_applications",
        "catering_quote_requests", "export_files",
        "push_tokens", "user_sessions", "coupons",
    ]:
        r = await db[coll].delete_many({})
        print(f"{coll}: deleted {r.deleted_count}")

    # Users: keep reviewer only
    r = await db.users.delete_many({"email": {"$ne": KEEP_REVIEWER}})
    print(f"users: deleted {r.deleted_count} (kept {KEEP_REVIEWER})")

    # Reset reviewer's loyalty balance for a clean e2e run
    ru = await db.users.update_one({"email": KEEP_REVIEWER}, {"$set": {"loyalty_points": 0}})
    print(f"reviewer loyalty reset: matched {ru.matched_count}")

    # Report what's kept
    for coll in ["master_menu", "weekly_menus", "catering_packages", "business_settings", "admins", "users"]:
        c = await db[coll].count_documents({})
        print(f"KEPT {coll}: {c} docs")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
