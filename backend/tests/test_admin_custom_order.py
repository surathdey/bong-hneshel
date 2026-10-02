"""Admin manual order: custom item + confirmation flow wiring."""
import asyncio, os, httpx
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
BASE = "http://localhost:8001"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@bong-hneshel.ca")
ADMIN_PW = os.environ["ADMIN_PASSWORD"]


async def main():
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{BASE}/api/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW})
        assert r.status_code == 200, r.text
        tok = r.json().get("token") or r.json().get("access_token")
        H = {"Authorization": f"Bearer {tok}"}

        # grab a delivery slot from the builder
        b = await c.get(f"{BASE}/api/admin/order-builder", headers=H)
        assert b.status_code == 200, b.text
        slots = b.json().get("delivery_slots") or []
        slot = slots[0] if slots else {"date": "2026-10-10", "window": "friday_delivery"}

        body = {
            "new_customer": {"name": "Custom Test", "phone": "+14165550111"},
            "items": [
                {"kind": "custom", "ref_id": "", "quantity": 2,
                 "custom_name": "Chef Special Thali", "custom_price_cents": 1899},
            ],
            "address": {"name": "Custom Test", "line1": "100 Queen St W", "city": "Toronto", "postal_code": "M5H 2N2", "province": "ON"},
            "slot": {"date": slot["date"], "window": slot["window"]},
            "phone": "+14165550111",
            "payment_method": "cod",
            "mark_as_paid": True,
        }
        r = await c.post(f"{BASE}/api/admin/orders/create", json=body, headers=H)
        assert r.status_code == 200, r.text
        order = r.json()["order"]
        items = order["items_snapshot"]
        assert len(items) == 1 and items[0]["kind"] == "custom", items
        assert items[0]["name"] == "Chef Special Thali"
        assert items[0]["unit_price_cents"] == 1899
        assert items[0]["line_total_cents"] == 3798  # 1899 * 2
        assert order["subtotal_cents"] == 3798
        assert order["payment_status"] == "paid"
        print("Custom item order created OK:", order["order_id"][-6:].upper(),
              "subtotal", order["subtotal_cents"], "total", order["total_cents"])
        print("ALL ADMIN CUSTOM ORDER TESTS PASSED ✅")


asyncio.run(main())
