import requests, datetime

B = "http://localhost:8001/api"

def login():
    r = requests.post(f"{B}/admin/login", json={"email": "admin@mustardgarden.ca", "password": "tlUYkZz1JnsD%Wy2"})
    r.raise_for_status()
    return r.json()["access_token"]

def main():
    tok = login()
    H = {"Authorization": f"Bearer {tok}"}

    # pick a far-future week to avoid clobbering real data
    ws = (datetime.date(2027, 1, 3)).isoformat()  # a Sunday
    # cleanup if exists
    requests.delete(f"{B}/admin/menus/{ws}", headers=H)

    # 1) create week with copy_all
    r = requests.post(f"{B}/admin/menus/create", headers=H, json={"week_start": ws, "copy_all_master": True})
    print("create:", r.status_code)
    assert r.status_code == 200, r.text
    menu = r.json()["menu"]
    lines = menu["lines"]
    print("  lines copied:", len(lines), "| title:", menu["title"])
    assert menu["title"] == f"Week of {ws}"
    assert all(l["is_visible"] is False for l in lines), "copied lines must be hidden"

    # duplicate create should 400
    r = requests.post(f"{B}/admin/menus/create", headers=H, json={"week_start": ws})
    print("dup create:", r.status_code)
    assert r.status_code == 400

    # 2) enable package so complimentary shows
    requests.post(f"{B}/admin/menus/{ws}/settings", headers=H, json={
        "package_enabled": True,
        "package": {"name": "Combo", "pick_count": 3, "price_cents": 3499, "eligible_master_ids": []},
    })

    # 3) set complimentary from first 2 master ids
    mids = [l["master_item_id"] for l in lines[:2]]
    r = requests.post(f"{B}/admin/menus/{ws}/complimentary", headers=H, json={"master_ids": mids})
    print("complimentary:", r.status_code)
    assert r.status_code == 200, r.text

    # 4) make one line visible, check hydrate + complimentary_items
    lid = lines[0]["line_id"]
    r = requests.post(f"{B}/admin/menus/{ws}/lines/{lid}/visibility", headers=H, json={"is_visible": True})
    print("visibility:", r.status_code)
    assert r.status_code == 200

    # verify via public-style hydration on that week: fetch admin menus and hydrate is only on /menu/current
    # instead, temporarily this week is future; use /menu/upcoming
    r = requests.get(f"{B}/menu/upcoming")
    ups = r.json()
    wk = next((x for x in ups if x["week_start"] == ws), None)
    assert wk is not None, "week not in upcoming"
    vis_items = wk.get("items", [])
    print("  visible items in hydrate:", len(vis_items))
    assert len(vis_items) == 1, f"expected 1 visible, got {len(vis_items)}"
    comps = wk.get("complimentary_items", [])
    print("  complimentary_items:", [c["name"] for c in comps])
    assert len(comps) == 2, f"expected 2 comps, got {len(comps)}"

    # 5) global always-available
    r = requests.post(f"{B}/admin/always-available", headers=H, json={"master_ids": mids})
    print("always set:", r.status_code)
    assert r.status_code == 200
    r = requests.get(f"{B}/menu/anytime")
    anytime = r.json()
    print("  anytime count:", len(anytime))
    assert len(anytime) == 2, f"expected 2 anytime, got {len(anytime)}"
    r = requests.get(f"{B}/admin/always-available", headers=H)
    assert set(r.json()["master_ids"]) == set(mids)

    # cleanup week + reset always list
    requests.delete(f"{B}/admin/menus/{ws}", headers=H)
    requests.post(f"{B}/admin/always-available", headers=H, json={"master_ids": []})
    print("ALL PASS")

if __name__ == "__main__":
    main()
