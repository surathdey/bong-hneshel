#!/usr/bin/env python3
"""
scrub_for_template.py
=====================

Prepares this repo to be pushed to `Curry-Co-Template` on GitHub by
stripping out tenant-specific credentials, secrets, and per-restaurant
identifiers so they don't leak into future forks (Jomidari, etc.).

WHAT THIS SCRIPT DOES
---------------------
1. `brand.json`                     → clears platform.tenant_id / api_key
2. `frontend/brand.config.js`       → clears platform.tenantId / apiKey
                                      (brand name & colors kept as
                                      "Curry & Co." reference defaults,
                                      per user preference)
3. `backend/.env`                   → blanks tenant-specific keys
                                      (GOOGLE_MAPS_API_KEY, EMERGENT_EMAIL_KEY,
                                      STRIPE_API_KEY, JWT_SECRET,
                                      INTEGRATIONS_FERNET_KEY, PUBLIC_BASE_URL,
                                      REVIEWER_* creds).
                                      LEAVES MONGO_URL, DB_NAME, ADMIN_*,
                                      EMAIL_FROM*, EMERGENT_LLM_KEY,
                                      EMERGENT_PUSH_KEY alone.
4. `memory/test_credentials.md`     → replaces with placeholder template.

WHAT THIS SCRIPT DOES *NOT* TOUCH
---------------------------------
- `backend/web_dist/`                 (kept, per user)
- `docs/seed-packs/curryco_seed_pack.json`  (kept, ships with template)
- Frontend brand colors / brand name  (kept as reference defaults)
- MongoDB / DB name in .env
- Admin default credentials in .env

USAGE
-----
    # Dry-run (default) — prints diff, writes nothing
    python scripts/scrub_for_template.py

    # Actually apply the scrub
    python scripts/scrub_for_template.py --apply

    # Apply and keep .pre-scrub.bak backups next to each edited file
    python scripts/scrub_for_template.py --apply --backup

    # Restore from previously-created backups
    python scripts/scrub_for_template.py --restore

The script is idempotent — running it twice is safe.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import sys
from pathlib import Path

# ─── Paths ──────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
BRAND_JSON = REPO_ROOT / "brand.json"
BRAND_CONFIG_JS = REPO_ROOT / "frontend" / "brand.config.js"
BACKEND_ENV = REPO_ROOT / "backend" / ".env"
TEST_CREDS = REPO_ROOT / "memory" / "test_credentials.md"

# ─── Constants ──────────────────────────────────────────────────────────
BACKUP_SUFFIX = ".pre-scrub.bak"

# Keys that should be blanked in backend/.env (per-tenant secrets).
ENV_KEYS_TO_BLANK = {
    "STRIPE_API_KEY": "",
    "GOOGLE_MAPS_API_KEY": "",
    "EMERGENT_EMAIL_KEY": "",
    "INTEGRATIONS_FERNET_KEY": "",
    "PUBLIC_BASE_URL": "",
    "REVIEWER_EMAIL": "",
    "REVIEWER_PASSWORD": "",
    # JWT secret must be regenerated per tenant
    "JWT_SECRET": "CHANGE_ME_generate_new_random_secret_per_tenant",
}

TEST_CREDS_PLACEHOLDER = """# Test credentials — TEMPLATE

> ⚠️ This file is a placeholder. Fill in real values for your restaurant
> after running `scripts/scrub_for_template.py` and re-seeding the DB.

## 🍎 App Store / Google Play REVIEWER account
- **Email:** `reviewer@<your-brand>.ca`
- **Password:** `<set-a-strong-password>`

## Delivery Partner
- URL: `/delivery-partner`
- Email: `delivery@<your-brand>.local`
- Password: `<set-a-strong-password>`

## Admin Portal
- URL: `/admin`
- Email: `admin@<your-brand>.local`
- Password: `<set-a-strong-password>`
- Default admin is seeded on backend startup from `ADMIN_EMAIL` + `ADMIN_PASSWORD`
  in `backend/.env`.

## Seed coupons (uppercase codes)
- `WELCOME10` — 10% off, min $20 subtotal
- `BENGALI15` — 15% off, min $50 subtotal
- `MISHTI5`   — $5 off, min $30 subtotal

## Backend seed endpoint
`POST /api/dev/seed` — populates current week menu + 2 future weeks, catering
packages, and coupons.
"""


# ─── Helpers ────────────────────────────────────────────────────────────
def _print_diff(label: str, before: str, after: str) -> None:
    if before == after:
        print(f"  · {label}: no change")
        return
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{label}",
        tofile=f"b/{label}",
        n=2,
    )
    print(f"\n  ── {label} ──")
    sys.stdout.writelines(diff)


def _write(path: Path, content: str, apply: bool, backup: bool) -> None:
    if not apply:
        return
    if backup and path.exists():
        bak = path.with_suffix(path.suffix + BACKUP_SUFFIX)
        if not bak.exists():
            shutil.copy2(path, bak)
    path.write_text(content, encoding="utf-8")


# ─── Scrubbers ──────────────────────────────────────────────────────────
def scrub_brand_json(apply: bool, backup: bool) -> None:
    if not BRAND_JSON.exists():
        print(f"  ! {BRAND_JSON} not found — skipping")
        return
    before = BRAND_JSON.read_text(encoding="utf-8")
    data = json.loads(before)
    platform = data.setdefault("platform", {})
    platform["tenant_id"] = ""
    platform["api_key"] = ""
    # Keep status_url + poll_seconds — they point at the shared control plane
    # and should be the same across tenants.
    after = json.dumps(data, indent=2) + "\n"
    _print_diff("brand.json", before, after)
    _write(BRAND_JSON, after, apply, backup)


def scrub_brand_config_js(apply: bool, backup: bool) -> None:
    if not BRAND_CONFIG_JS.exists():
        print(f"  ! {BRAND_CONFIG_JS} not found — skipping")
        return
    before = BRAND_CONFIG_JS.read_text(encoding="utf-8")
    after = before
    # Clear tenantId + apiKey inside the platform: { ... } block.
    after = re.sub(
        r'(tenantId:\s*)"[^"]*"',
        r'\1""',
        after,
    )
    after = re.sub(
        r'(apiKey:\s*)"[^"]*"',
        r'\1""',
        after,
    )
    _print_diff("frontend/brand.config.js", before, after)
    _write(BRAND_CONFIG_JS, after, apply, backup)


def scrub_backend_env(apply: bool, backup: bool) -> None:
    if not BACKEND_ENV.exists():
        print(f"  ! {BACKEND_ENV} not found — skipping")
        return
    before = BACKEND_ENV.read_text(encoding="utf-8")
    lines_out: list[str] = []
    for raw in before.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            lines_out.append(raw)
            continue
        m = re.match(r'^([A-Z0-9_]+)\s*=\s*(.*)$', raw)
        if not m:
            lines_out.append(raw)
            continue
        key = m.group(1)
        if key in ENV_KEYS_TO_BLANK:
            new_val = ENV_KEYS_TO_BLANK[key]
            # preserve quoting style — always use double quotes for safety
            lines_out.append(f'{key}="{new_val}"')
        else:
            lines_out.append(raw)
    after = "\n".join(lines_out)
    # keep trailing newline if the original had one
    if before.endswith("\n") and not after.endswith("\n"):
        after += "\n"
    _print_diff("backend/.env", before, after)
    _write(BACKEND_ENV, after, apply, backup)


def scrub_test_credentials(apply: bool, backup: bool) -> None:
    if not TEST_CREDS.parent.exists():
        print(f"  ! {TEST_CREDS.parent} not found — skipping")
        return
    before = TEST_CREDS.read_text(encoding="utf-8") if TEST_CREDS.exists() else ""
    after = TEST_CREDS_PLACEHOLDER
    _print_diff("memory/test_credentials.md", before, after)
    _write(TEST_CREDS, after, apply, backup)


# ─── Restore ────────────────────────────────────────────────────────────
def restore_backups() -> int:
    targets = [BRAND_JSON, BRAND_CONFIG_JS, BACKEND_ENV, TEST_CREDS]
    restored = 0
    for p in targets:
        bak = p.with_suffix(p.suffix + BACKUP_SUFFIX)
        if bak.exists():
            shutil.copy2(bak, p)
            print(f"  ✓ restored {p.relative_to(REPO_ROOT)} from {bak.name}")
            restored += 1
        else:
            print(f"  · no backup for {p.relative_to(REPO_ROOT)}")
    return restored


# ─── Main ───────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scrub tenant-specific values from this repo before pushing to Curry-Co-Template."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write changes (default is dry-run).",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Save .pre-scrub.bak copies of files before overwriting (only with --apply).",
    )
    parser.add_argument(
        "--restore",
        action="store_true",
        help="Restore any files that have .pre-scrub.bak backups and exit.",
    )
    args = parser.parse_args()

    if args.restore:
        print("Restoring from .pre-scrub.bak backups…")
        n = restore_backups()
        print(f"\nRestored {n} file(s).")
        return 0

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"scrub_for_template.py — mode: {mode}")
    print(f"repo root: {REPO_ROOT}\n")

    print("Scrubbing:")
    scrub_brand_json(args.apply, args.backup)
    scrub_brand_config_js(args.apply, args.backup)
    scrub_backend_env(args.apply, args.backup)
    scrub_test_credentials(args.apply, args.backup)

    print("\nDone.")
    if not args.apply:
        print("\nThis was a DRY-RUN. Re-run with --apply to write changes.")
        print("Add --backup to keep .pre-scrub.bak copies for easy rollback.")
    else:
        print("\n✓ Files scrubbed. Manual checklist before pushing:")
        print("  1. `git status` — confirm only expected files changed.")
        print("  2. `git diff brand.json frontend/brand.config.js backend/.env memory/test_credentials.md`")
        print("  3. Consider whether `backend/.env` should be committed at all")
        print("     (usually .env is gitignored; template forks recreate it).")
        print("  4. Rebuild web bundle if you want a clean template SPA:")
        print("       cd frontend && npx expo export -p web && \\")
        print("       rm -rf ../backend/web_dist && mv dist ../backend/web_dist")
        print("  5. Commit + push to Curry-Co-Template.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
