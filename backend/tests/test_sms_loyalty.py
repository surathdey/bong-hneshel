"""Verify loyalty details in customer SMS + items in owner SMS."""
import asyncio, os
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
import server

captured = []


async def fake_send(settings, to, body):
    captured.append((to, body))


async def main():
    server._send_sms_via_settings = fake_send

    order = {
        "order_id": "ord_test_abc123",
        "address": {"name": "Priya Sharma", "email": "", "line1": "100 Queen St W", "city": "Toronto"},
        "phone": "+14165551234",
        "total_cents": 5499,
        "subtotal_cents": 6499,
        "points_redeemed": 500,
        "points_redeemed_cents": 500,
        "payment_method": "cod",
        "items_snapshot": [
            {"name": "Butter Chicken", "quantity": 2, "line_total_cents": 3998},
            {"name": "Egg Tarka Fry", "quantity": 1, "line_total_cents": 1499},
        ],
        "slot": {"window": "evening", "date": "2026-10-02"},
    }
    settings = {
        "loyalty_enabled": True,
        "loyalty_redeem_points_per_dollar": 100,
        "notify_phone": "+14374999453",
        "notify_email": "",
    }
    user_doc = {"role": "customer", "loyalty_points": 1250, "name": "Priya Sharma"}

    await server._notify_order_created(order, settings, user_doc)

    cust = [b for (to, b) in captured if to == "+14165551234"]
    owner = [b for (to, b) in captured if to == "+14374999453"]
    assert cust, "no customer SMS captured"
    assert owner, "no owner SMS captured"
    cbody, obody = cust[0], owner[0]

    print("========== CUSTOMER SMS ==========")
    print(cbody)
    print("========== OWNER SMS ==========")
    print(obody)
    print("==================================")

    # Customer SMS assertions
    assert "Loyalty used: 500 pts (saved CA$5.00)" in cbody, "loyalty-used line missing/incorrect"
    assert "You have 1250 loyalty points remaining (~CA$12.50)." in cbody, "remaining balance line missing/incorrect"
    assert "Butter Chicken" in cbody and "Total: CA$54.99" in cbody

    # Owner SMS assertions
    assert "New order #ABC123" in obody
    assert "Butter Chicken x2" in obody and "Egg Tarka Fry x1" in obody, "items missing in owner SMS"
    assert "Total CA$54.99" in obody

    # Guest → no remaining-balance line
    captured.clear()
    guest_user = {"role": "guest", "loyalty_points": 0}
    order2 = dict(order, points_redeemed=0, points_redeemed_cents=0, phone="+14165550000")
    await server._notify_order_created(order2, settings, guest_user)
    gcust = [b for (to, b) in captured if to == "+14165550000"][0]
    assert "loyalty points remaining" not in gcust, "guest should not see balance line"
    assert "Loyalty used" not in gcust, "no points used → no loyalty-used line"
    print("Guest SMS (no loyalty lines) OK")

    print("\nALL SMS LOYALTY TESTS PASSED ✅")


asyncio.run(main())
