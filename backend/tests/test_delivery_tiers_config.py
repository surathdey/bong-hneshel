import requests
B = "http://localhost:8001/api"

def admin_h():
    r = requests.post(f"{B}/admin/login", json={"email": "admin@mustardgarden.ca", "password": "tlUYkZz1JnsD%Wy2"})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}

def guest_h():
    r = requests.post(f"{B}/auth/guest"); r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['session_token']}"}

def item():
    return (requests.get(f"{B}/menu/current").json().get("items") or [])[0]

def quote(H, addr):
    it = item()
    body = {"items": [{"kind": "menu", "ref_id": it["item_id"], "quantity": 1}],
            "address": addr, "slot": {"date": "2026-09-06", "window": "sunday_evening"},
            "phone": "4160000000", "payment_method": "cod"}
    r = requests.post(f"{B}/orders/quote", headers=H, json=body); assert r.status_code == 200, r.text
    d = r.json(); return d["delivery_fee_cents"], d.get("delivery_distance_km"), d.get("delivery_fee_tier")

def main():
    AH = admin_h(); GH = guest_h()
    orig = requests.get(f"{B}/admin/settings", headers=AH).json()

    # configure custom tiers: 0-5 FREE, 5-1000 $20
    patch = {**orig, "key": "default",
             "kitchen_address": "6941 Derry Rd West, Milton, ON, Canada",
             "delivery_fee_tiers": [{"max_km": 5, "fee_cents": 0}, {"max_km": 1000, "fee_cents": 2000}],
             "delivery_fee_over_max_cents": 5000}
    r = requests.put(f"{B}/admin/settings", headers=AH, json=patch); assert r.status_code == 200, r.text

    toronto = {"name": "T", "line1": "100 Queen St W", "city": "Toronto", "province": "ON", "postal_code": "M5H2N2"}
    fee, km, tier = quote(GH, toronto)
    print("Toronto w/ custom tiers:", fee, km, tier)
    assert fee == 2000, f"expected 2000, got {fee}"

    milton = {"name": "M", "line1": "x", "city": "Milton", "province": "ON", "postal_code": "L9T1N2", "lat": 43.5162, "lng": -79.8827}
    fee, km, tier = quote(GH, milton)
    print("Milton w/ custom tiers:", fee, km, tier)
    assert fee == 0, f"expected 0, got {fee}"

    # restore original tiers
    requests.put(f"{B}/admin/settings", headers=AH, json={**orig, "key": "default"})
    print("ALL PASS (restored)")

if __name__ == "__main__":
    main()
