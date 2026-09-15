"""
================================================================
 Suparna Dey Platform · Phone-Home Client
================================================================

Curry & Co. (and every rebranded fork) polls the central control
plane every N minutes to fetch its tenancy + subscription status.

The response drives runtime enforcement:
    • operational       — false → block ALL customer traffic
    • hide_checkout     — hide the Place-Order button in the cart
    • show_banner       — render an admin banner ("Subscription past due" etc.)
    • block_driver_app  — refuse driver logins

Wire-up:
    server.py::@app.on_event("startup") spawns start_platform_poller()
    server.py::/api/platform/status returns the last-cached response
    server.py::various endpoints check `is_operational()` before serving

Design notes:
    • Latest status is cached in-process (module-level dict) so the hot path
      never hits the network. Stale cache is preferable to a stalled request.
    • Failures never propagate — they just log a warning and reuse the last
      known status. Platform outages must not take down the restaurant.
    • Zero-config safe: if brand.json has no `platform.tenant_id`, the poller
      is a no-op. This lets the codebase run standalone in dev/preview.
================================================================
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

from brand import (
    PLATFORM_TENANT_ID, PLATFORM_API_KEY, PLATFORM_STATUS_URL, PLATFORM_POLL_SEC,
)

log = logging.getLogger("curryco.platform")


# ---------------------------------------------------------------------------
# In-memory cache. Populated on first successful poll; consulted by the
# `is_operational()` gate on every hot-path request.
_status: Dict[str, Any] = {
    "known": False,                     # true after first successful poll
    "operational": True,                # OPEN by default so dev/preview boots fine
    "hide_checkout": False,
    "show_banner": False,
    "block_driver_app": False,
    "banner_text": "",
    "subscription_status": None,
    "subscription_plan": None,          # populated post-first-poll — stable shape pre-poll
    "current_period_end": None,         # ditto
    "checked_at": None,
    "last_error": None,
}

_task: Optional[asyncio.Task] = None


def configured() -> bool:
    """True when brand.json + env have wired this tenant to a platform."""
    return bool(PLATFORM_TENANT_ID and PLATFORM_API_KEY and PLATFORM_STATUS_URL)


def snapshot() -> Dict[str, Any]:
    """Read-only view of the last-known platform status.
    Exposed via `GET /api/platform/status` and used by the admin banner."""
    return dict(_status)


def is_operational() -> bool:
    """Cheap boolean check used by hot-path routes (checkout, driver login).
    Defaults OPEN if we've never spoken to the platform (fail-open)."""
    return bool(_status.get("operational", True))


def should_hide_checkout() -> bool:
    return bool(_status.get("hide_checkout", False))


def should_block_driver() -> bool:
    return bool(_status.get("block_driver_app", False))


# ---------------------------------------------------------------------------
# Fetch + poll implementation
# ---------------------------------------------------------------------------
async def _fetch_once() -> None:
    """One phone-home call. Never raises — captures failures into `_status.last_error`."""
    if not configured():
        return
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            r = await http.get(
                PLATFORM_STATUS_URL,
                headers={
                    "X-Tenant-Id": PLATFORM_TENANT_ID,
                    "X-Tenant-Api-Key": PLATFORM_API_KEY,
                },
            )
        if r.status_code == 401:
            # Auth failure means the api_key was rotated on the platform. Rare
            # but critical — surface it loudly in the banner so ops notices.
            _status.update({
                "known": True,
                "operational": False,
                "show_banner": True,
                "banner_text": "Tenant credentials rejected by the platform. Ops action required.",
                "last_error": "401 Unauthorized",
                "checked_at": datetime.now(timezone.utc).isoformat(),
            })
            log.error("platform phone-home 401 — rotate api_key or contact platform ops")
            return
        r.raise_for_status()
        data = r.json()

        enforcement = data.get("enforcement") or {}
        sub = data.get("subscription") or {}
        _status.update({
            "known": True,
            "operational":       bool(enforcement.get("operational", True)),
            "hide_checkout":     bool(enforcement.get("hide_checkout", False)),
            "show_banner":       bool(enforcement.get("show_banner", False)),
            "block_driver_app":  bool(enforcement.get("block_driver_app", False)),
            "banner_text":       enforcement.get("banner_text", "") or _default_banner(data),
            "subscription_status": sub.get("status"),
            "subscription_plan":   sub.get("plan"),
            "current_period_end":  sub.get("current_period_end"),
            "checked_at":         data.get("checked_at") or datetime.now(timezone.utc).isoformat(),
            "last_error":         None,
        })
    except Exception as exc:  # noqa: BLE001 — any failure keeps the last-known state
        _status["last_error"] = f"{type(exc).__name__}: {exc}"
        _status["checked_at"] = datetime.now(timezone.utc).isoformat()
        log.warning(f"platform phone-home failed: {_status['last_error']}")


def _default_banner(data: Dict[str, Any]) -> str:
    """Fallback banner text used when the platform doesn't send its own copy.
    All messages emphasize that the RESTAURANT OWNER — not the customer — is
    responsible for the subscription lapse, so end-users don't feel accused."""
    sub = data.get("subscription") or {}
    if sub.get("status") == "past_due":
        return (
            "The restaurant owner's platform subscription payment is past due. "
            "Ordering will resume once billing is settled."
        )
    if sub.get("status") == "trialing":
        return (
            f"Restaurant owner: your platform trial ends "
            f"{(sub.get('current_period_end') or '')[:10]}. Add a payment method to avoid interruption."
        )
    if sub.get("status") == "cancelled":
        return (
            "The restaurant owner has cancelled their platform subscription. "
            "Ordering is paused until they reactivate."
        )
    return ""


async def _poll_forever() -> None:
    """Backoff-aware infinite loop. Doubles the interval on consecutive errors
    up to 30 min to keep the platform load bounded when it's down."""
    backoff = PLATFORM_POLL_SEC
    while True:
        await _fetch_once()
        if _status.get("last_error"):
            backoff = min(backoff * 2, 1800)  # 30-min cap
        else:
            backoff = PLATFORM_POLL_SEC
        await asyncio.sleep(backoff)


def start_platform_poller() -> None:
    """Kick off the poller once, at FastAPI startup.
    Safe to call multiple times — subsequent calls are a no-op."""
    global _task
    if _task is not None and not _task.done():
        return
    if not configured():
        log.info("platform poller skipped (brand.json has no `platform.tenant_id`)")
        return
    log.info(
        f"platform poller starting → tenant={PLATFORM_TENANT_ID} "
        f"poll_seconds={PLATFORM_POLL_SEC}"
    )
    _task = asyncio.create_task(_poll_forever())


async def stop_platform_poller() -> None:
    """Graceful shutdown hook for tests + reloads."""
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except (asyncio.CancelledError, Exception):
            pass
        _task = None
