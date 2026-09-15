# 🌱 Seed Packs — Bootstrap a new tenant with a working catalog

A **seed pack** is a portable JSON file (~60 KB) that captures the reusable content of a live tenant: dishes, weekly menus, catering packages, coupons, delivery zones, and business settings — minus PII and brand-specific fields.

Use this when you fork the Curry-Co-Template into a new brand (Jomidari, etc.) and want your admin portal to open with a fully populated menu on day one, ready to be rebranded item-by-item.

---

## 📦 Available packs

| File                                                          | Source brand   | Rows | Generated |
| ------------------------------------------------------------- | -------------- | ---- | --------- |
| [`curryco_seed_pack.json`](./curryco_seed_pack.json)         | Curry & Co.    | 58   | Aug 2026  |

Content of `curryco_seed_pack.json`:

- **46** master menu items (Bengali & Indian dishes with images, descriptions, spice levels, veg tags)
- **3** weekly menu templates
- **5** catering packages
- **3** coupon codes
- **1** business settings row (with brand-identifying fields blanked — filled by `brand.json` on the target)

---

## 🚀 How to use a seed pack in a new tenant

### On the source (Curry & Co.) — export

```bash
cd backend
python3 -m tools.seed_export --out /app/seed_pack.json
```

Optional flags:
```bash
python3 -m tools.seed_export --skip coupons delivery_zones
python3 -m tools.seed_export --out /tmp/only_menu.json --skip weekly_menus catering_packages coupons business_settings
```

### On the target (Jomidari) — import

1. **Paste the JSON file** into the Jomidari Emergent chat (drag-and-drop into the chat box, or use the paperclip icon).
2. In your prompt, tell the agent:

   > *"Import this seed pack into the current tenant DB. Use `python3 -m tools.seed_import <path>`. Then restart backend and take a screenshot of the admin menu page — it should show all 46 dishes."*

3. The agent will run:
   ```bash
   cd backend
   python3 -m tools.seed_import /app/docs/seed-packs/curryco_seed_pack.json
   ```
4. If you want a clean slate first:
   ```bash
   python3 -m tools.seed_import curryco_seed_pack.json --wipe --i-know
   ```

---

## 🔐 What is stripped before export

The exporter deliberately drops these to keep the pack tenant-safe:

- MongoDB `_id`, `created_at`, `updated_at`, `created_by`, `updated_by`
- `business_settings.business_name`, `email`, `phone`, `kitchen_address`, `company_info` — belong in `brand.json`, not the seed pack
- `payment_methods.*.publishable_key`, `secret_key`, `client_id`, `client_secret`, `webhook_secret`, `email`, `instructions` — blanked, structure preserved
- `catering_packages.contact_email` — brand-specific
- `coupons.usage_count`, `redeemed_by` — start-of-life on the target

---

## 🛡 Import guardrails

- **Self-import refused** — if the seed pack's `_meta.source_brand` matches the target tenant's `brand.json → key`, the importer aborts. Prevents you from accidentally overwriting Curry & Co.'s live catalog with an old Curry & Co. dump.
- **Idempotent upsert** — running the import twice inserts nothing new the second time. Rows are keyed on `item_id`, `menu_id` / `week_start`, `package_id`, `code`, `zone_id`, or `key`.
- **`--wipe` requires `--i-know`** — no accidental catalog wipes.
- **No user data ever crosses tenants** — users, orders, admins, payment_transactions, and delivery_partners are NOT exported.

---

## 🍴 Recommended workflow when forking a new brand

```
┌──────────────────────────────┐        ┌─────────────────────────────┐
│  Curry & Co. (source)        │        │  Jomidari (fork target)     │
│                              │        │                             │
│  1. python3 -m tools.seed_   │        │  4. Rebrand: brand.config.  │
│     export --out seed.json   │        │     js + brand.json (via    │
│                              │        │     agent chat)             │
│  2. Download seed.json ──────┼───────►│                             │
│                              │        │  5. Paste seed.json in chat │
│  3. (Optional) commit under  │        │                             │
│     docs/seed-packs/         │        │  6. Agent runs seed_import  │
│                              │        │                             │
│                              │        │  7. Admin menu shows 46     │
│                              │        │     dishes → rename them    │
│                              │        │     to Jomidari-specific    │
│                              │        │     items over the next     │
│                              │        │     week                    │
└──────────────────────────────┘        └─────────────────────────────┘
```

---

## 💡 Advanced usage

### Cherry-pick collections

```bash
python3 -m tools.seed_import curryco_seed_pack.json --only master_menu
```

### Combine multiple packs (blend two brands' dish catalogs)

```bash
python3 -m tools.seed_import curryco_seed_pack.json --only master_menu
python3 -m tools.seed_import competitor_seed_pack.json --only master_menu
# → target now has both catalogs; deduplicate by name/item_id if needed
```

### Emergency rollback

Every import overwrites by primary key. To roll back:
```bash
mongodump --uri "$MONGO_URL" --out backup_before_import/
python3 -m tools.seed_import curryco_seed_pack.json
# if something went wrong:
mongorestore --uri "$MONGO_URL" --drop backup_before_import/
```

---

## 🧭 Where these scripts live

- Exporter: `backend/tools/seed_export.py`
- Importer: `backend/tools/seed_import.py`
- Both are pure `motor` (async MongoDB) — no extra deps beyond what the backend already ships.
