"""
Iteration 16 — verify the startup-build step + SPA route serving.

Emergent Support fix: /app/backend/server.py runs _try_build_web_bundle() at
module-import time. If /app/frontend/dist/index.html is missing, it invokes
`npx expo export --platform web --output-dir dist` before the SPA static
mounts and catch-all are registered.

These tests hit the PUBLIC ingress URL (EXPO_BACKEND_URL from frontend/.env)
so we exercise the same routing K8s ingress uses in prod.
"""
import os
import re
from pathlib import Path

import pytest
import requests

# NOTE ON URL CHOICE:
# The Emergent PREVIEW ingress (curry-ecosystem.preview.emergentagent.com)
# SPLITS traffic — /api/* → backend:8001, everything else (/, /admin, /_expo/*,
# /health) → Expo dev server on :3000. So hitting the preview URL for SPA/
# static/health paths would test Expo dev, not the backend SPA fix.
#
# The PRODUCTION ingress (curry-ecosystem.emergent.host) routes ALL paths to
# backend:8001. That's where the startup-build fix in server.py actually runs
# in production.
#
# For the backend fix under test, we exercise the backend DIRECTLY at
# localhost:8001 — this is the exact HTTP handler that prod ingress hits.
# We ALSO probe the deployed production URL to record its live state.
BASE_URL = "http://localhost:8001"
PROD_URL = "https://curry-ecosystem.emergent.host"

# For API-only tests we can still use the public preview URL because /api/* IS
# proxied through ingress to :8001.
_ENV = Path("/app/frontend/.env").read_text()
_m = re.search(r"^EXPO_PUBLIC_BACKEND_URL=(\S+)", _ENV, re.M)
PREVIEW_URL = _m.group(1).rstrip("/") if _m else BASE_URL

WEB_DIST = Path("/app/frontend/dist")


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"User-Agent": "curryco-tests/16"})
    return sess


# --- Health probe (K8s readiness) ---------------------------------------
class TestHealth:
    def test_health_returns_200_json(self, s):
        r = s.get(f"{BASE_URL}/health", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "ok"


# --- Startup build produced dist/index.html -----------------------------
class TestBuildArtifact:
    def test_index_html_exists_on_disk(self):
        assert (WEB_DIST / "index.html").exists(), \
            "dist/index.html missing — startup build did not run"

    def test_expo_static_js_exists(self):
        js_dir = WEB_DIST / "_expo" / "static" / "js" / "web"
        assert js_dir.exists()
        assert any(js_dir.glob("entry-*.js")), "no entry-*.js in _expo/static/js/web"


# --- SPA HTML routes should return 200 text/html ------------------------
class TestSPARoutes:
    def _assert_html(self, r):
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        ct = r.headers.get("content-type", "")
        assert "text/html" in ct, f"content-type={ct!r}"
        # index.html shipped by Expo has a <div id="root"> (or an app root
        # element) — assert we're serving actual HTML, not the diagnostic
        # 'Web bundle not deployed' page.
        body = r.text.lower()
        assert "web bundle not deployed" not in body, (
            "SPA fallback is serving the diagnostic page, not dist/index.html"
        )
        assert "<html" in body

    def test_admin_returns_spa_html(self, s):
        r = s.get(f"{BASE_URL}/admin", timeout=20, allow_redirects=False)
        self._assert_html(r)

    def test_admin_dashboard_returns_spa_html(self, s):
        r = s.get(f"{BASE_URL}/admin/dashboard", timeout=20, allow_redirects=False)
        self._assert_html(r)


# --- Expo static JS bundle mount ----------------------------------------
class TestExpoStatic:
    def test_entry_js_served_via_mount(self, s):
        # discover the entry-*.js name that Expo just produced
        js_files = list((WEB_DIST / "_expo" / "static" / "js" / "web").glob("entry-*.js"))
        assert js_files, "no entry-*.js file produced by expo export"
        js_name = js_files[0].name
        url = f"{BASE_URL}/_expo/static/js/web/{js_name}"
        r = s.get(url, timeout=20)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        ct = r.headers.get("content-type", "")
        assert "javascript" in ct or "application/js" in ct or "text/js" in ct, \
            f"unexpected content-type={ct!r}"
        # File should be non-empty JS
        assert len(r.content) > 500


class TestFavicon:
    def test_favicon_200(self, s):
        r = s.get(f"{BASE_URL}/favicon.ico", timeout=15)
        assert r.status_code == 200


# --- Existing API routes must not be broken by SPA catch-all ------------
class TestApiRoutesStillWork:
    def test_menu_current_still_works(self, s):
        r = s.get(f"{BASE_URL}/api/menu/current", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # menu/current returns an object with items OR a doc — just assert it's json-ish
        assert isinstance(data, (dict, list))

    def test_admin_login_returns_jwt(self, s):
        payload = {
            "email": os.environ.get("ADMIN_EMAIL", "admin@curryandco.local"),
            "password": os.environ.get("ADMIN_PASSWORD", "curry@admin2026"),
        }
        # /api routes ARE proxied through preview ingress, so hit the public URL
        r = s.post(f"{PREVIEW_URL}/api/admin/login", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "access_token" in data
        assert len(data["access_token"]) > 20

    def test_legal_privacy_returns_html(self, s):
        r = s.get(f"{BASE_URL}/api/legal/privacy", timeout=15)
        assert r.status_code == 200, r.text
        ct = r.headers.get("content-type", "")
        assert "text/html" in ct, f"content-type={ct!r}"
        assert "<html" in r.text.lower() or "privacy" in r.text.lower()


# --- Log grep: confirms module correctly initialized SPA mounts ---------
class TestBackendLogs:
    def test_serving_spa_true_in_logs(self):
        log_paths = [
            "/var/log/supervisor/backend.err.log",
            "/var/log/supervisor/backend.out.log",
        ]
        joined = ""
        for p in log_paths:
            fp = Path(p)
            if fp.exists():
                joined += fp.read_text(errors="replace")
        assert "[web-build] serving SPA=True" in joined, (
            "expected '[web-build] serving SPA=True' in backend logs — startup "
            "build did not report success"
        )


# --- Deployed PRODUCTION URL smoke check --------------------------------
# The whole reason for this fix: users visiting https://curry-ecosystem.emergent.host/admin
# should see the actual Expo SPA, not the 'Web Bundle Missing' diagnostic
# page and not a 404 for the JS bundle. If these tests fail, the fix is
# NOT working in the live production container even though it works locally.
class TestProductionDeployedURL:
    def test_prod_health_returns_json(self, s):
        r = s.get(f"{PROD_URL}/health", timeout=20)
        assert r.status_code == 200, r.text
        assert r.json().get("status") == "ok"

    def test_prod_admin_serves_actual_spa_not_diagnostic(self, s):
        r = s.get(f"{PROD_URL}/admin", timeout=20, allow_redirects=False)
        assert r.status_code == 200, r.text
        body = r.text.lower()
        assert "web bundle not deployed" not in body, (
            "PROD is still serving the diagnostic 'Web bundle not deployed' "
            "page — the startup-time build is NOT running (or is failing) in "
            "the production container. Live URL: " + PROD_URL + "/admin"
        )

    def test_prod_expo_static_js_returns_200(self, s):
        js_files = list((WEB_DIST / "_expo" / "static" / "js" / "web").glob("entry-*.js"))
        if not js_files:
            pytest.skip("no local entry-*.js to match against")
        js_name = js_files[0].name
        r = s.get(f"{PROD_URL}/_expo/static/js/web/{js_name}", timeout=20)
        assert r.status_code == 200, (
            f"PROD /_expo/static/js/web/{js_name} returned {r.status_code}. "
            "Startup build did not populate dist/ in the production container."
        )
