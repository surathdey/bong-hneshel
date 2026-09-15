import requests
B = "http://localhost:8001/api"

def guest():
    r = requests.post(f"{B}/auth/guest"); r.raise_for_status(); return r.json()["session_token"]

def main():
    H = {"Authorization": f"Bearer {guest()}"}
    cur = requests.get(f"{B}/menu/current").json()
    item = (cur.get("items") or [])[0]
    body = {
        "items": [{"kind": "menu", "ref_id": item["item_id"], "quantity": 2}],
        "address": {"name": "Test Buyer", "email": "buyer@example.com", "line1": "30 Main St E",
                    "city": "Milton", "province": "ON", "postal_code": "L9T1N2"},
        "slot": {"date": "2026-09-06", "window": "sunday_evening"},
        "phone": "4160001111", "payment_method": "cod",
    }
    r = requests.post(f"{B}/orders", headers=H, json=body)
    assert r.status_code == 200, r.text
    o = r.json()
    oid = o["order_id"]
    print("order:", oid, "total", o["total_cents"], "email saved:", o["address"].get("email"))
    assert o["address"].get("email") == "buyer@example.com"
    inv = requests.get(f"{B}/invoice/{oid}")
    print("invoice:", inv.status_code, "has PDF button:", "Save PDF" in inv.text or "download" in inv.text.lower())
    assert inv.status_code == 200

    # interac order note
    body2 = {**body, "payment_method": "interac"}
    r2 = requests.post(f"{B}/orders", headers=H, json=body2)
    assert r2.status_code == 200, r2.text
    print("interac order:", r2.json()["order_id"])
    print("ALL PASS")

if __name__ == "__main__":
    main()
