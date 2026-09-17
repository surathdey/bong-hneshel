# Bong Hneshel — Backend API Test Suite

Automated pytest suite covering the FastAPI backend (`/api/*`). It hits a **running**
backend over HTTP, so it validates real routing, auth, and DB behaviour end‑to‑end.

## What's covered
| File | Area |
|------|------|
| `test_public_api.py`   | Public/unauthenticated reads: settings, brand, menus, catering, platform status, privacy, coupon lookup, secret‑leak guard |
| `test_customer_api.py` | Guest auth, `/auth/me`, orders list, saved address create/delete, first‑time coupon, order quote |
| `test_admin_api.py`    | Admin login, all admin GET dashboards, auth rejection, coupon CRUD round‑trip + validation |
| `test_delivery_api.py` | Delivery‑partner auth guards + login/apply validation |
| `test_security_api.py` | Regression: `menu/upsert`, `orders/{id}/status`, `dev/seed` must require admin; invoice no‑500 |

## Prerequisites
- Backend running (locally it's on `http://localhost:8001` via supervisor).
- `pytest` and `httpx` installed (both already in the backend environment).
- Valid admin credentials (defaults match `/app/memory/test_credentials.md`).

## Run it
```bash
# from repo root
cd backend/tests/api
./run_api_tests.sh

# or against the deployed/preview host
BASE_URL=https://clone-verify-2.preview.emergentagent.com ./run_api_tests.sh

# or plain pytest
BASE_URL=http://localhost:8001 python -m pytest backend/tests/api -v
```

## Configuration (env vars)
| Var | Default | Purpose |
|-----|---------|---------|
| `BASE_URL` | `http://localhost:8001` | API origin (suite appends `/api`) |
| `ADMIN_EMAIL` | `admin@bong-hneshel.ca` | admin login |
| `ADMIN_PASSWORD` | *(from test_credentials.md)* | admin login |
| `API_TIMEOUT` | `30` | per‑request timeout (seconds) |

## Notes
- Tests are **non‑destructive**: the only writes are a temporary saved address and a
  temporary coupon (`PYTEST…`), both deleted in the same test. No orders are placed,
  no payments are charged, and `dev/seed` is never invoked (only its auth guard is checked).
- The order‑quote test **skips** automatically if the menu has no purchasable items,
  and passes on either `200` (window open) or `400` (ordering window closed).
- Run only one area, e.g.:
  ```bash
  python -m pytest backend/tests/api/test_admin_api.py -v
  ```
