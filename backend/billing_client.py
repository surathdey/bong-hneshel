"""
================================================================
 Suparna Dey Platform · Billing Client
================================================================

Thin, cache-friendly HTTP client for the Suparna Dey central hub's
Stripe-Billing endpoints. This module is what the tenant admin
portal's "Billing" tab talks to.

Design:
    • The hub owns Stripe. This tenant never sees Stripe keys.
    • We proxy 3 endpoints:
          GET  <hub>/api/tenant/billing/summary
          POST <hub>/api/tenant/billing/checkout      → { url }
          POST <hub>/api/tenant/billing/portal        → { url }
    • Summary is cached in-process for 60s so refreshing the tab
      doesn't hammer the hub, but is short enough that a fresh
      subscribe/cancel shows up quickly.
    • Auth uses the same tenant headers as `platform_client.py`.
    • Failures degrade gracefully — the UI stays functional and
      shows a "hub unavailable, try later" state.

Zero-config safe: if brand.json has no `platform.tenant_id`, all
calls short-circuit and return `{status: "unconfigured"}`.
================================================================
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional
from urllib.parse import urljoin, urlparse

import httpx

from brand import (
    PLATFORM_TENANT_ID, PLATFORM_API_KEY, PLATFORM_STATUS_URL,
)

log = logging.getLogger("curryco.billing")

# 60-second in-process cache for the summary endpoint. Keep it small so
# fresh subscription state (post-checkout) surfaces quickly.
_CACHE_TTL_SEC = 60
_summary_cache: Dict[str, Any] = {"at": 0.0, "value": None}

# HTTP timeout — the hub call happens on-demand from the Billing tab, so
# we can afford a slightly higher ceiling than the background poller.
_HTTP_TIMEOUT = 12.0


# ---------------------------------------------------------------------------
# Derive the hub base URL from the existing PLATFORM_STATUS_URL so we don't
# force the user to configure two URLs. Given
#   https://control-plane-11.preview.emergentagent.com/api/tenant/status
# we derive
#   https://control-plane-11.preview.emergentagent.com/
# and hang billing endpoints off it.
def _hub_base() -> str:
    if not PLATFORM_STATUS_URL:
        return ""
    p = urlparse(PLATFORM_STATUS_URL)
    return f"{p.scheme}://{p.netloc}"


def _url(path: str) -> str:
    base = _hub_base()
    if not base:
        return ""
    return urljoin(base + "/", path.lstrip("/"))


def configured() -> bool:
    """True when brand.json + env have wired this tenant to a platform."""
    return bool(PLATFORM_TENANT_ID and PLATFORM_API_KEY and _hub_base())


def _headers() -> Dict[str, str]:
    return {
        "X-Tenant-Id": PLATFORM_TENANT_ID,
        "X-Tenant-Api-Key": PLATFORM_API_KEY,
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Empty-state response shapes. These MUST match what the hub returns for
# real cases — the UI treats "unconfigured" and "unreachable" as terminal
# states and shows a helpful empty state instead of a broken card.
def _unconfigured() -> Dict[str, Any]:
    return {
        "status": "unconfigured",
        "message": "This tenant is not connected to a platform yet. "
                   "Set `platform.tenant_id` and `platform.api_key` in brand.json.",
        "plan": None,
        "invoices": [],
        "card": None,
    }


def _unreachable(err: str) -> Dict[str, Any]:
    return {
        "status": "unreachable",
        "message": "Could not reach the Suparna Dey Platform. Try again shortly.",
        "error": err,
        "plan": None,
        "invoices": [],
        "card": None,
    }


# ---------------------------------------------------------------------------
async def get_summary(force: bool = False) -> Dict[str, Any]:
    """Fetch (or return cached) billing summary from the hub.

    Cached for 60s. Pass `force=True` to bypass the cache after a
    checkout redirect.
    """
    if not configured():
        return _unconfigured()

    now = time.time()
    if not force and _summary_cache["value"] is not None and (now - _summary_cache["at"]) < _CACHE_TTL_SEC:
        return _summary_cache["value"]

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as http:
            r = await http.get(_url("/api/tenant/billing/summary"), headers=_headers())
        if r.status_code == 401:
            return {"status": "unauthorized", "message": "Tenant credentials rejected by the platform."}
        if r.status_code == 404:
            # Hub hasn't shipped billing endpoints yet — treat as "no subscription"
            # so the UI shows the Subscribe CTA. This is the common pre-Phase-3
            # state.
            fallback = {
                "status": "not_implemented",
                "message": "The platform hasn't enabled billing yet.",
                "plan": None,
                "invoices": [],
                "card": None,
            }
            _summary_cache.update({"at": now, "value": fallback})
            return fallback
        r.raise_for_status()
        data = r.json()

        # Normalise a couple of fields so the frontend never has to
        # defend against missing keys.
        data.setdefault("plan", None)
        data.setdefault("invoices", [])
        data.setdefault("card", None)
        data.setdefault("status", "none")

        _summary_cache.update({"at": now, "value": data})
        return data
    except Exception as exc:  # noqa: BLE001
        log.warning(f"billing summary fetch failed: {type(exc).__name__}: {exc}")
        return _unreachable(f"{type(exc).__name__}: {exc}")


async def create_checkout(success_url: str, cancel_url: str) -> Dict[str, Any]:
    """Ask the hub for a Stripe Checkout URL. Returns `{url}` on success."""
    if not configured():
        return {"error": "unconfigured", "message": "Tenant not wired to platform."}
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as http:
            r = await http.post(
                _url("/api/tenant/billing/checkout"),
                headers=_headers(),
                json={"success_url": success_url, "cancel_url": cancel_url},
            )
        if r.status_code >= 400:
            return {"error": f"hub_{r.status_code}", "message": r.text[:400]}
        # Invalidate cache — subscription state is about to change.
        _summary_cache.update({"at": 0.0, "value": None})
        return r.json()
    except Exception as exc:  # noqa: BLE001
        return {"error": "unreachable", "message": f"{type(exc).__name__}: {exc}"}


async def create_portal(return_url: str) -> Dict[str, Any]:
    """Ask the hub for a Stripe Customer Portal URL. Returns `{url}` on success."""
    if not configured():
        return {"error": "unconfigured", "message": "Tenant not wired to platform."}
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as http:
            r = await http.post(
                _url("/api/tenant/billing/portal"),
                headers=_headers(),
                json={"return_url": return_url},
            )
        if r.status_code >= 400:
            return {"error": f"hub_{r.status_code}", "message": r.text[:400]}
        # Portal edits (cancel/update card) invalidate the cached summary too.
        _summary_cache.update({"at": 0.0, "value": None})
        return r.json()
    except Exception as exc:  # noqa: BLE001
        return {"error": "unreachable", "message": f"{type(exc).__name__}: {exc}"}


def invalidate_cache() -> None:
    """Test hook + used after a Stripe webhook echoes back to this tenant."""
    _summary_cache.update({"at": 0.0, "value": None})
