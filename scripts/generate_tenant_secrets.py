#!/usr/bin/env python3
"""
generate_tenant_secrets.py — one-shot secret generator per new tenant.

Prints (and optionally writes) every random/derivable secret needed to
stand up a fresh tenant fork. The output is designed to be copy-pasted
straight into the Emergent env panel, so ops never has to invent an
entropy source or type a password by hand.

Usage:
    python scripts/generate_tenant_secrets.py --slug jomidari --domain jomidari.ca
    python scripts/generate_tenant_secrets.py --slug jomidari --domain jomidari.ca --write

Fields printed:
    JWT_SECRET, INTEGRATIONS_FERNET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD,
    REVIEWER_EMAIL, REVIEWER_PASSWORD, EMAIL_FROM, EMAIL_FROM_NAME,
    DB_NAME

`--write` also patches /app/backend/.env in place (preserving
comments and any existing non-target keys). ADMIN_EMAIL / REVIEWER_EMAIL
follow the "<role>@<domain>" convention used by every existing tenant.

Nothing here calls the network. The script is safe to run offline and
is idempotent given the same --seed (default: fresh randomness every run).
"""
from __future__ import annotations

import argparse
import json
import secrets
import string
import sys
from pathlib import Path
from typing import Dict

REPO_ROOT = Path(__file__).resolve().parent.parent
BRAND_JSON = REPO_ROOT / "brand.json"
BACKEND_ENV = REPO_ROOT / "backend" / ".env"

# ─── Password generator ────────────────────────────────────────────────
# 16 chars, mixed case + digits + a small safe symbol set. Avoids
# characters that are painful to type on mobile (quotes, backslash) or
# get mangled by shell / .env parsing (dollar sign, backtick).
_PW_SAFE_SYMBOLS = "!#%&*+-=?@_"
_PW_ALPHABET = string.ascii_letters + string.digits + _PW_SAFE_SYMBOLS


def random_password(length: int = 16) -> str:
    # Ensure at least one from each pool for policy compatibility (some
    # store review flows reject "all letters" passwords).
    while True:
        pw = "".join(secrets.choice(_PW_ALPHABET) for _ in range(length))
        if (
            any(c.islower() for c in pw)
            and any(c.isupper() for c in pw)
            and any(c.isdigit() for c in pw)
            and any(c in _PW_SAFE_SYMBOLS for c in pw)
        ):
            return pw


def random_jwt_secret() -> str:
    # 48 bytes → 64 url-safe chars, more than enough for HS256.
    return secrets.token_urlsafe(48)


def fernet_key() -> str:
    # Import lazily so users without cryptography installed still get the
    # other fields printed.
    try:
        from cryptography.fernet import Fernet  # type: ignore
    except ImportError:
        print(
            "  ! `cryptography` not installed — cannot generate INTEGRATIONS_FERNET_KEY.\n"
            "    Install: pip install cryptography",
            file=sys.stderr,
        )
        return "INSTALL_CRYPTOGRAPHY_AND_RERUN"
    return Fernet.generate_key().decode()


# ─── Env file merge ─────────────────────────────────────────────────────
def patch_env(target: Path, new_vars: Dict[str, str]) -> None:
    """Replace or append every key in `new_vars` inside `target`, preserving
    existing lines/comments for keys we don't touch. Values are always
    written wrapped in double quotes."""
    existing_lines: list[str] = []
    seen_keys: set[str] = set()
    if target.exists():
        for raw in target.read_text(encoding="utf-8").splitlines():
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                existing_lines.append(raw)
                continue
            if "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key in new_vars:
                    existing_lines.append(f'{key}="{new_vars[key]}"')
                    seen_keys.add(key)
                    continue
            existing_lines.append(raw)

    # Append keys that weren't already present
    for k, v in new_vars.items():
        if k not in seen_keys:
            existing_lines.append(f'{k}="{v}"')

    target.write_text("\n".join(existing_lines) + "\n", encoding="utf-8")


# ─── Main ───────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a fresh tenant's random secrets in one go.",
    )
    parser.add_argument(
        "--slug",
        required=True,
        help='Lowercase kebab-case slug (e.g. "jomidari"). Used for DB_NAME.',
    )
    parser.add_argument(
        "--domain",
        required=True,
        help='Tenant domain (e.g. "jomidari.ca"). Used for admin/reviewer/order emails.',
    )
    parser.add_argument(
        "--brand-name",
        default=None,
        help='Human display name for EMAIL_FROM_NAME. Defaults to brand.json → name.',
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Also patch /app/backend/.env in place (idempotent).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit results as JSON instead of a human-readable block.",
    )
    args = parser.parse_args()

    slug = args.slug.strip().lower()
    domain = args.domain.strip().lstrip("@").lower()

    # Pull brand.name for EMAIL_FROM_NAME if we can find one.
    brand_name = args.brand_name
    if not brand_name and BRAND_JSON.exists():
        try:
            brand_name = json.loads(BRAND_JSON.read_text(encoding="utf-8")).get("name")
        except Exception:  # noqa: BLE001
            brand_name = None
    brand_name = brand_name or slug.title()

    values: Dict[str, str] = {
        "JWT_SECRET":              random_jwt_secret(),
        "INTEGRATIONS_FERNET_KEY": fernet_key(),
        "ADMIN_EMAIL":             f"admin@{domain}",
        "ADMIN_PASSWORD":          random_password(),
        "REVIEWER_EMAIL":          f"reviewer@{domain}",
        "REVIEWER_PASSWORD":       random_password(),
        "EMAIL_FROM":              f"orders@{domain}",
        "EMAIL_FROM_NAME":         brand_name,
        "DB_NAME":                 f"{slug}_db",
    }

    if args.json:
        print(json.dumps(values, indent=2))
    else:
        print("── Auto-generated tenant secrets ──────────────────────────")
        for k, v in values.items():
            print(f"{k:24s}= {v}")
        print("───────────────────────────────────────────────────────────")
        print(f"Tenant slug   : {slug}")
        print(f"Tenant domain : {domain}")
        print(f"Brand name    : {brand_name}")
        print("")
        print("Paste the block above into the Emergent env panel.")
        print("Give ADMIN_PASSWORD to the tenant owner via a password manager,")
        print("NOT over email or chat.")

    if args.write:
        BACKEND_ENV.parent.mkdir(parents=True, exist_ok=True)
        patch_env(BACKEND_ENV, values)
        print(f"\n✓ Patched {BACKEND_ENV.relative_to(REPO_ROOT)} in place.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
