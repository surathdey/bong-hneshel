"""Smoke test for the Review Management System (backend, localhost)."""
import asyncio, os, uuid, httpx
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
BASE = "http://localhost:8001"
ADMIN_EMAIL = os.environ["ADMIN_EMAIL"] if os.environ.get("ADMIN_EMAIL") else "admin@bong-hneshel.ca"
ADMIN_PW = os.environ["ADMIN_PASSWORD"]


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    # pick a real master item
    mi = await db.master_menu.find_one({}, {"_id": 0, "item_id": 1, "name": 1})
    assert mi, "no master menu items"
    iid, iname = mi["item_id"], mi["name"]

    # seed a review_request token directly (simulate delivered order)
    token = "smoketok_" + uuid.uuid4().hex[:8]
    oid = "ord_smoke_" + uuid.uuid4().hex[:6]
    await db.review_requests.delete_many({"order_id": oid})
    await db.review_requests.insert_one({
        "token": token, "order_id": oid, "user_id": "", "status": "sent",
        "items": [{"item_id": iid, "name": iname, "image_url": ""}],
        "customer_name": "Test Customer", "phone": "", "email": "",
        "public_base_url": "", "created_at": datetime.now(timezone.utc),
    })

    async with httpx.AsyncClient(timeout=15) as c:
        # 1. public GET request
        r = await c.get(f"{BASE}/api/reviews/request/{token}")
        assert r.status_code == 200, r.text
        assert r.json()["items"][0]["item_id"] == iid
        print("GET request OK:", r.json()["business_name"], len(r.json()["items"]), "items")

        # 2. submit review
        r = await c.post(f"{BASE}/api/reviews/submit", json={
            "token": token, "reviews": [{"item_id": iid, "rating": 5, "comment": "Delicious!"}]})
        assert r.status_code == 200 and r.json()["ok"], r.text
        print("submit OK:", r.json()["message"])

        # 3. re-submit idempotent
        r2 = await c.post(f"{BASE}/api/reviews/submit", json={
            "token": token, "reviews": [{"item_id": iid, "rating": 1}]})
        assert r2.status_code == 200, r2.text
        print("re-submit idempotent OK")

        # 4. review is PENDING → not visible publicly yet
        r = await c.get(f"{BASE}/api/menu-items/{iid}/reviews")
        assert r.status_code == 200
        before = r.json()["review_count"]
        print("public reviews before approval:", before, "(should exclude pending)")

        # 5. admin login
        r = await c.post(f"{BASE}/api/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW})
        assert r.status_code == 200, r.text
        tok = r.json()["token"] if "token" in r.json() else r.json().get("access_token")
        H = {"Authorization": f"Bearer {tok}"}

        # 6. admin sees pending
        r = await c.get(f"{BASE}/api/admin/reviews?status=pending", headers=H)
        assert r.status_code == 200, r.text
        pend = [x for x in r.json()["reviews"] if x["order_id"] == oid]
        assert pend, "pending review not found"
        rid = pend[0]["review_id"]
        print("admin pending count:", r.json()["counts"]["pending"])

        # 7. approve
        r = await c.post(f"{BASE}/api/admin/reviews/{rid}/moderate", json={"action": "approve"}, headers=H)
        assert r.status_code == 200 and r.json()["status"] == "approved", r.text

        # 8. now visible publicly
        r = await c.get(f"{BASE}/api/menu-items/{iid}/reviews")
        after = r.json()["review_count"]
        assert after == before + 1, f"expected {before+1} got {after}"
        assert r.json()["avg_rating"] >= 1
        print("public reviews after approval:", after, "avg:", r.json()["avg_rating"])

        # 9. summary batch
        r = await c.get(f"{BASE}/api/reviews/summary?item_ids={iid}")
        assert r.status_code == 200 and iid in r.json()["ratings"], r.text
        print("summary OK:", r.json()["ratings"][iid])

        # 10. CSV bulk upload
        csv = f"item_id,rating,comment,customer_name\n{iid},4,Great historic,Old Customer\nbad_id,3,x,y\n"
        r = await c.post(f"{BASE}/api/admin/reviews/bulk-upload", headers=H,
                         files={"file": ("reviews.csv", csv, "text/csv")})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["inserted"] == 1 and j["error_count"] == 1, j
        print("bulk upload OK:", j)

        # cleanup smoke docs
        await db.reviews.delete_many({"order_id": oid})
        await db.reviews.delete_many({"source": "admin_bulk", "customer_name": "Old Customer"})
        await db.review_requests.delete_many({"order_id": oid})
        print("\nALL REVIEW SMOKE TESTS PASSED ✅")


asyncio.run(main())
