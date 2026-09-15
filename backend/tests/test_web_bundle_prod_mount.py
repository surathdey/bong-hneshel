"""
Iteration 17 — verify /app/backend/web_dist/ is served as the SPA bundle
so production K8s image (which only ships /app/backend/) can render /admin.

Tests cover:
  1. GET /health
  2. GET /admin   (200 text/html, actual SPA, not diagnostic)
  3. GET /admin/dashboard  (SPA catch-all)
  4. GET /_expo/static/js/web/entry-*.js (bundle mount from web_dist)
  5. GET /favicon.ico
  6. GET /api/menu/current (existing API not broken)
  7. POST /api/admin/login → JWT
  8. GET /api/health/web-bundle diagnostic fields
  9. Simulate prod: move /app/frontend/ away, restart backend, /admin still 200
     — proves standalone operation from /app/backend/web_dist.
"""
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest
import requests


BASE_URL = "http://localhost:8001"
WEB_DIST_PROD = Path("/app/backend/web_dist")
FRONTEND_DIR = Path("/app/frontend")
FRONTEND_BAK = Path("/tmp/_frontend_bak")

_ENV = Path("/app/frontend/.env").read_text()
_m = re.search(r"^EXPO_PUBLIC_BACKEND_URL=(\S+)", _ENV, re.M)
PREVIEW_URL = _m.group(1).rstrip("/") if _m else BASE_URL


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"User-Agent": "curryco-tests/17"})
    return sess


def _wait_for_backend(url=f"{BASE_URL}/health", timeout=45):
    start = time.time()
    last_err = None
    while time.time() - start < timeout:
        try:
            r = requests.get(url, timeout=3)
            if r.status_code == 200:
                return True
        except Exception as e:  # noqa
            last_err = e
        time.sleep(1)
    raise RuntimeError(f"backend not ready after {timeout}s: {last_err}")


# -------------------------------------------------------------------
# 1. K8s probe
# -------------------------------------------------------------------
class TestHealth:
    def test_health_returns_200_json(self, s):
        r = s.get(f"{BASE_URL}/health", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "ok"


# -------------------------------------------------------------------
# 2 & 3. SPA HTML routes
# -------------------------------------------------------------------
class TestSPARoutes:
    def _assert_html(self, r):
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        ct = r.headers.get("content-type", "")
        assert "text/html" in ct, f"content-type={ct!r}"
        body = r.text.lower()
        assert "web bundle not deployed" not in body, (
            "SPA fallback served the diagnostic page, not real index.html"
        )
        assert "<html" in body

    def test_admin_returns_spa_html(self, s):
        r = s.get(f"{BASE_URL}/admin", timeout=20, allow_redirects=False)
        self._assert_html(r)

    def test_admin_dashboard_returns_spa_html(self, s):
        r = s.get(f"{BASE_URL}/admin/dashboard", timeout=20, allow_redirects=False)
        self._assert_html(r)


# -------------------------------------------------------------------
# 4. /_expo/static/js/web/entry-*.js served from web_dist mount
# -------------------------------------------------------------------
class TestExpoStatic:
    def test_entry_js_served_via_mount(self, s):
        js_dir = WEB_DIST_PROD / "_expo" / "static" / "js" / "web"
        assert js_dir.exists(), f"missing {js_dir}"
        js_files = list(js_dir.glob("entry-*.js"))
        assert js_files, "no entry-*.js in web_dist/_expo/static/js/web"
        js_name = js_files[0].name
        url = f"{BASE_URL}/_expo/static/js/web/{js_name}"
        r = s.get(url, timeout=20)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        ct = r.headers.get("content-type", "")
        assert "javascript" in ct or "application/js" in ct, \
            f"unexpected content-type={ct!r}"
        assert len(r.content) > 500


# -------------------------------------------------------------------
# 5. favicon.ico
# -------------------------------------------------------------------
class TestFavicon:
    def test_favicon_200(self, s):
        r = s.get(f"{BASE_URL}/favicon.ico", timeout=15)
        assert r.status_code == 200
        assert len(r.content) > 100


# -------------------------------------------------------------------
# 6 & 7. API routes still work
# -------------------------------------------------------------------
class TestApiRoutesStillWork:
    def test_menu_current(self, s):
        r = s.get(f"{BASE_URL}/api/menu/current", timeout=15)
        assert r.status_code == 200, r.text
        # doc may be dict (menu present) or None (empty)
        data = r.json()
        assert data is None or isinstance(data, (dict, list))

    def test_admin_login_returns_jwt(self, s):
        payload = {
            "email": os.environ.get("ADMIN_EMAIL", "admin@curryandco.local"),
            "password": os.environ.get("ADMIN_PASSWORD", "curry@admin2026"),
        }
        r = s.post(f"{BASE_URL}/api/admin/login", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "access_token" in data
        assert len(data["access_token"]) > 20


# -------------------------------------------------------------------
# 8. Diagnostic health endpoint reflects web_dist source
# -------------------------------------------------------------------
class TestWebBundleDiagnostic:
    def test_diagnostic_present_and_size(self, s):
        r = s.get(f"{BASE_URL}/api/health/web-bundle", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("present") is True, d
        assert "/web_dist" in (d.get("source") or ""), \
            f"expected source under /web_dist, got {d.get('source')}"
        assert d.get("dist_size_bytes", 0) > 1_000_000, \
            f"dist_size_bytes too small: {d.get('dist_size_bytes')}"


# -------------------------------------------------------------------
# 9. THE CRITICAL PROD SIMULATION.
#    Move /app/frontend/ → /tmp/_frontend_bak, restart backend, /admin
#    must still serve 200 HTML (proving the bundle in /app/backend/web_dist
#    works standalone). Then restore /app/frontend.
# -------------------------------------------------------------------
class TestProdSimulationWithoutFrontend:
    """Order last — this restarts the backend twice."""

    @classmethod
    def teardown_class(cls):
        # Always restore, even if a test above failed.
        if FRONTEND_BAK.exists() and not FRONTEND_DIR.exists():
            try:
                shutil.move(str(FRONTEND_BAK), str(FRONTEND_DIR))
            except Exception:
                pass
        # Restart backend one more time to leave a clean state.
        try:
            subprocess.run(["sudo", "supervisorctl", "restart", "backend"],
                           check=False, timeout=30,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            _wait_for_backend()
        except Exception:
            pass

    def test_z_simulate_prod_only_container(self, s):
        assert FRONTEND_DIR.exists(), "sanity: /app/frontend must exist at start"
        # 1. Move frontend away.
        if FRONTEND_BAK.exists():
            shutil.rmtree(FRONTEND_BAK)
        shutil.move(str(FRONTEND_DIR), str(FRONTEND_BAK))
        assert not FRONTEND_DIR.exists()
        try:
            # 2. Restart backend (fresh import — must re-resolve web_dist
            #    without /app/frontend/dist).
            res = subprocess.run(
                ["sudo", "supervisorctl", "restart", "backend"],
                check=False, timeout=30,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            assert res.returncode == 0, res.stderr.decode(errors="replace")
            _wait_for_backend()

            # 3. Health probe
            r = s.get(f"{BASE_URL}/health", timeout=10)
            assert r.status_code == 200

            # 4. Diagnostic — frontend_source_shipped should be False now,
            #    source should be /app/backend/web_dist.
            r = s.get(f"{BASE_URL}/api/health/web-bundle", timeout=10)
            assert r.status_code == 200
            d = r.json()
            assert d.get("present") is True, d
            assert d.get("source") == str(WEB_DIST_PROD), d
            assert d.get("frontend_source_shipped") is False, d

            # 5. THE MONEY SHOT — /admin still serves 200 HTML.
            r = s.get(f"{BASE_URL}/admin", timeout=15, allow_redirects=False)
            assert r.status_code == 200, r.text[:300]
            assert "text/html" in r.headers.get("content-type", "")
            assert "web bundle not deployed" not in r.text.lower(), \
                "prod simulation still shows diagnostic page — fix not working"

            # 6. Static JS bundle also served.
            js_dir = WEB_DIST_PROD / "_expo" / "static" / "js" / "web"
            js_files = list(js_dir.glob("entry-*.js"))
            assert js_files
            js_name = js_files[0].name
            r = s.get(f"{BASE_URL}/_expo/static/js/web/{js_name}", timeout=15)
            assert r.status_code == 200, f"js bundle status {r.status_code}"
        finally:
            # 7. Restore /app/frontend
            if FRONTEND_DIR.exists():
                # unexpected — shouldn't have been recreated
                pass
            else:
                shutil.move(str(FRONTEND_BAK), str(FRONTEND_DIR))
            # 8. Restart backend to leave the pod clean for later tests.
            subprocess.run(["sudo", "supervisorctl", "restart", "backend"],
                           check=False, timeout=30,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            _wait_for_backend()
