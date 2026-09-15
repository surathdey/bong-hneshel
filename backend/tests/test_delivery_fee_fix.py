import requests

B = "http://localhost:8001/api"

def customer_token():
    r = requests.post(f"{B}/auth/guest")
    r.raise_for_status()
    return r.json()["session_token"]

def a_menu_item():
    cur = requests.get(f"{B}/menu/current").json()
    items = cur.get("items") or []
    assert items, "no visible items in current week"
    return items[0]

def quote(H, address):
    item = a_menu_item()
    body = {
        "items": [{"kind": "menu", "ref_id": item["item_id"], "quantity": 1}],
        "address": address,
        "slot": {"date": "2026-09-06", "window": "sunday_evening"},
        "phone": "4160000000",
        "payment_method": "cod",
    }
    r = requests.post(f"{B}/orders/quote", headers=H, json=body)
    assert r.status_code == 200, r.text
    d = r.json()
    return d["delivery_fee_cents"], d.get("delivery_distance_km"), d.get("delivery_fee_tier")

def main():
    H = {"Authorization": f"Bearer {customer_token()}"}

    # 1) Milton coords -> should be FREE (0-20km)
    fee, km, tier = quote(H, {"name": "Test", "line1": "123 Main St", "city": "Milton",
                              "province": "ON", "postal_code": "L9T1N2", "lat": 43.5162, "lng": -79.8827})
    print("Milton coords:", fee, km, tier)
    assert fee == 0, f"expected FREE, got {fee}"

    # 2) Toronto (old bug: default city) -> ~59.7km -> $10
    fee, km, tier = quote(H, {"name": "Test", "line1": "123 Main St", "city": "Toronto",
                              "province": "ON", "postal_code": "M5V0A0"})
    print("Toronto text:", fee, km, tier)
    assert fee == 1000, f"expected 1000, got {fee}"

    # 3) Milton by TEXT (no coords) -> FREE
    fee, km, tier = quote(H, {"name": "Test", "line1": "30 Main St E", "city": "Milton",
                              "province": "ON", "postal_code": "L9T1N2"})
    print("Milton text:", fee, km, tier)
    assert fee == 0, f"expected FREE, got {fee}"

    print("ALL PASS")

if __name__ == "__main__":
    main()
