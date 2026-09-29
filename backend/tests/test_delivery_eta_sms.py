"""Verify delivery ETA SMS reaches ALL customers (not only guests)."""
import asyncio, os
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
import server

captured = []
async def fake_send(settings, to, body):
    captured.append((to, body))
async def fake_push(recipients=None, data=None):
    return None


async def main():
    server._send_sms_via_settings = fake_send
    server.send_push = fake_push

    settings = {"integrations": {"twilio": {"account_sid": "x", "auth_token_encrypted": "y", "from_number": "+1"}}}
    order = {
        "order_id": "ord_eta_test99",
        "user_id": "usr_1",
        "address": {"name": "Priya Sharma"},
        "phone": "+14165551234",
        "delivery_eta_seconds": 1500,  # 25 min
    }

    # tentative (driver sets out)
    captured.clear()
    await server._notify_customer_eta(order, settings, exact=False)
    assert captured, "no SMS sent for registered customer (tentative)"
    tentative = captured[0][1]
    print("TENTATIVE SMS:\n", tentative, "\n")
    assert "out for delivery" in tentative
    assert "25 min" in tentative
    assert "Track live:" in tentative

    # exact (1 stop away)
    captured.clear()
    await server._notify_customer_eta(order, settings, exact=True)
    exact = captured[0][1]
    print("EXACT SMS:\n", exact, "\n")
    assert "you're next" in exact
    assert "25 min" in exact
    assert "Track live:" in exact

    print("ALL DELIVERY ETA SMS TESTS PASSED ✅")


asyncio.run(main())
