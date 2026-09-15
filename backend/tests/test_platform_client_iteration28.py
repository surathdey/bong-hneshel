"""
Iteration 28 — Suparna Dey Platform phone-home client tests.

Covers:
  1. GET /api/platform/status shape + poller health (HTTP, live backend)
  2. Poller populated `known=True` + subscription_status within ~10s of boot
  3. Regression: POST /api/orders NOT 402 when operational=True   (HTTP live)
  4. Regression: POST /api/delivery/login NOT 402 when operational=True (HTTP live)
  5. Gate: patch platform_client._status → POST /api/orders returns 402
     with the banner_text echoed (TestClient in-process, direct cache poke)
  6. Gate: patch block_driver_app=True → POST /api/delivery/login returns 402
     (TestClient in-process)

Design note:
  Tests (5)/(6) must poke the SAME `_status` dict the gate code reads. Because
  the supervisord backend is a different process, we run those two tests via
  `fastapi.testclient.TestClient` on the SAME code — that gives us direct
  access to `platform_client._status`.  We monkey-patch `_fetch_once` to a
  no-op BEFORE startup so the real 5-minute poller can't clobber our patch
  mid-test.
"""
import os
import sys
import pytest
import requests

# Make /app/backend importable for in-process TestClient tests.
sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    "https://curry-ecosystem.preview.emergentagent.com",
).rstrip("/")

DELIVERY_EMAIL = "delivery@curryandco.local"  # seeded alt (per test_credentials.md)
DELIVERY_PASSWORD = "curry@delivery2026"


# ---------------------------------------------------------------
# 1 + 2 — live status endpoint (HTTP)
# ---------------------------------------------------------------
class TestPlatformStatusEndpoint:
    def test_status_returns_200_with_expected_fields(self):
        r = requests.get(f"{BASE_URL}/api/platform/status", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        expected = {
            "known", "operational", "hide_checkout", "show_banner",
            "block_driver_app", "banner_text", "subscription_status",
            "checked_at",
        }
        missing = expected - set(data.keys())
        assert not missing, f"missing keys: {missing} · got={list(data.keys())}"

    def test_poller_reached_control_plane(self):
        """Within ~10s of backend startup, `known` should be true and
        subscription_status populated (poller has phoned home at least once)."""
        r = requests.get(f"{BASE_URL}/api/platform/status", timeout=15)
        data = r.json()
        assert data["known"] is True, (
            f"platform cache still unknown — poller likely never reached "
            f"control plane. last_error={data.get('last_error')}"
        )
        assert data["subscription_status"], "subscription_status is empty/None"
        assert data["checked_at"], "checked_at not set"
        # Curry is currently active on the control plane
        assert data["operational"] is True, (
            f"Curry should be operational: {data}"
        )
        # These flags should also be false in current live state
        assert data["hide_checkout"] is False
        assert data["block_driver_app"] is False


# ---------------------------------------------------------------
# 3 + 4 — regression via live HTTP: no accidental 402s
# ---------------------------------------------------------------
class TestGatesInactiveWhenOperational:
    def test_orders_not_402_when_operational(self):
        """Empty cart → 400 is fine. What we're proving is the platform gate
        does not FALSELY block the endpoint when operational=True."""
        rg = requests.post(f"{BASE_URL}/api/auth/guest", timeout=10)
        assert rg.status_code == 200, rg.text
        token = rg.json()["session_token"]

        payload = {
            "items": [],
            "address": {"line1": "1 TEST_iter28", "postal_code": "M5S1A1"},
            "slot": {"date": "2099-01-01", "window": "friday_evening"},
            "phone": "+14165550101",
            "payment_method": "cod",
        }
        r = requests.post(
            f"{BASE_URL}/api/orders",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        assert r.status_code != 402, (
            f"platform gate falsely rejected order while operational=True: "
            f"{r.status_code} {r.text}"
        )

    def test_delivery_login_success_when_not_blocked(self):
        r = requests.post(
            f"{BASE_URL}/api/delivery/login",
            json={"email": DELIVERY_EMAIL, "password": DELIVERY_PASSWORD},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "access_token" in body
        assert body.get("partner", {}).get("email") == DELIVERY_EMAIL

    def test_delivery_login_wrong_pw_is_401_not_402(self):
        r = requests.post(
            f"{BASE_URL}/api/delivery/login",
            json={"email": DELIVERY_EMAIL, "password": "TEST_iter28_wrong"},
            timeout=15,
        )
        # Must be 401 (credential rejection), NOT 402 (platform gate).
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"


# ---------------------------------------------------------------
# 5 + 6 — In-process gate simulation via TestClient + direct cache poke
# ---------------------------------------------------------------
@pytest.fixture(scope="module")
def inproc_client():
    """Boot the FastAPI app in-process with the real platform poller
    disabled, so our _status patches are stable for the entire test."""
    import platform_client

    # Neutralise the real HTTP poller BEFORE FastAPI startup event fires.
    async def _noop_fetch():
        return None
    platform_client._fetch_once = _noop_fetch  # type: ignore

    # Import server AFTER monkey-patching so start_platform_poller() uses
    # the neutered _fetch_once inside its loop.
    from server import app
    from fastapi.testclient import TestClient

    with TestClient(app) as tc:
        yield tc, platform_client


class TestOrderGateOnSuspension:
    def test_orders_returns_402_when_hide_checkout(self, inproc_client):
        tc, plat = inproc_client
        original = dict(plat._status)
        try:
            plat._status.update({
                "known": True,
                "operational": False,
                "hide_checkout": True,
                "banner_text": "test suspended TEST_iter28",
            })
            # Auth
            rg = tc.post("/api/auth/guest")
            assert rg.status_code == 200, rg.text
            token = rg.json()["session_token"]

            payload = {
                "items": [],
                "address": {"line1": "1 TEST_iter28", "postal_code": "M5S1A1"},
                "slot": {"date": "2099-01-01", "window": "friday_evening"},
                "phone": "+14165550101",
                "payment_method": "cod",
            }
            r = tc.post(
                "/api/orders",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 402, (
                f"expected 402 when platform suspends, got {r.status_code}: "
                f"{r.text}"
            )
            assert "test suspended TEST_iter28" in r.text, (
                f"banner_text should appear in body: {r.text}"
            )
        finally:
            plat._status.clear()
            plat._status.update(original)

    def test_orders_returns_402_when_operational_false_only(self, inproc_client):
        """Confirm operational=False alone (without hide_checkout) also gates."""
        tc, plat = inproc_client
        original = dict(plat._status)
        try:
            plat._status.update({
                "known": True,
                "operational": False,
                "hide_checkout": False,
                "banner_text": "operational off TEST_iter28",
            })
            rg = tc.post("/api/auth/guest")
            token = rg.json()["session_token"]
            payload = {
                "items": [],
                "address": {"line1": "1 TEST_iter28", "postal_code": "M5S1A1"},
                "slot": {"date": "2099-01-01", "window": "friday_evening"},
                "phone": "+14165550101",
                "payment_method": "cod",
            }
            r = tc.post(
                "/api/orders",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 402, r.text
            assert "operational off TEST_iter28" in r.text
        finally:
            plat._status.clear()
            plat._status.update(original)


class TestDeliveryLoginGateOnBlock:
    def test_delivery_login_returns_402_when_blocked(self, inproc_client):
        tc, plat = inproc_client
        original = dict(plat._status)
        try:
            plat._status.update({
                "known": True,
                "block_driver_app": True,
                "banner_text": "driver blocked TEST_iter28",
            })
            r = tc.post(
                "/api/delivery/login",
                json={"email": DELIVERY_EMAIL, "password": DELIVERY_PASSWORD},
            )
            assert r.status_code == 402, (
                f"expected 402 for blocked driver, got {r.status_code}: {r.text}"
            )
            assert "driver blocked TEST_iter28" in r.text
        finally:
            plat._status.clear()
            plat._status.update(original)

    def test_delivery_login_gate_precedes_credential_check(self, inproc_client):
        """Even wrong credentials must return 402 (not 401) when block is on —
        the gate is enforced BEFORE password verification, preventing
        credential-stuffing during a suspension."""
        tc, plat = inproc_client
        original = dict(plat._status)
        try:
            plat._status.update({
                "known": True,
                "block_driver_app": True,
                "banner_text": "driver blocked TEST_iter28",
            })
            r = tc.post(
                "/api/delivery/login",
                json={"email": DELIVERY_EMAIL, "password": "TEST_iter28_wrong"},
            )
            assert r.status_code == 402, r.text
        finally:
            plat._status.clear()
            plat._status.update(original)
