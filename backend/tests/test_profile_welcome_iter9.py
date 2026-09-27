"""Iteration 9 backend tests — Profile update + welcome-email hook."""
import os
import uuid
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"
BASE_URL = BASE_URL.rstrip("/")

session = requests.Session()
session.headers.update({"Content-Type": "application/json"})


def _register_user():
    email = f"TEST_iter9_{uuid.uuid4().hex[:10]}@example.com"
    payload = {"email": email, "password": "TestPass123!", "name": "Iter9 Tester"}
    r = session.post(f"{BASE_URL}/api/auth/register", json=payload, timeout=15)
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    body = r.json()
    return email, body["session_token"], body["user"]


# ---------------- POST /api/me/profile ----------------

def test_profile_update_requires_auth():
    r = session.post(f"{BASE_URL}/api/me/profile", json={"phone": "+14165551234"}, timeout=10)
    assert r.status_code == 401, f"expected 401, got {r.status_code} — {r.text}"


def test_profile_update_sets_phone_and_name():
    email, token, user = _register_user()
    assert user.get("phone") in (None, ""), f"new user should have no phone, got {user.get('phone')!r}"

    new_name = "Iter9 Updated Name"
    new_phone = "+14165550199"
    r = session.post(
        f"{BASE_URL}/api/me/profile",
        json={"name": new_name, "phone": new_phone},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert body["user"]["phone"] == new_phone
    assert body["user"]["name"] == new_name

    # Verify persistence via /auth/me
    me = session.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert me.status_code == 200
    assert me.json()["phone"] == new_phone
    assert me.json()["name"] == new_name


def test_profile_update_clears_phone_with_empty_string():
    _, token, _ = _register_user()
    # First set it
    r = session.post(
        f"{BASE_URL}/api/me/profile",
        json={"phone": "+14165550100"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert r.status_code == 200 and r.json()["user"]["phone"] == "+14165550100"

    # Now clear with empty string -> becomes None
    r2 = session.post(
        f"{BASE_URL}/api/me/profile",
        json={"phone": ""},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["user"]["phone"] in (None,), f"expected None, got {r2.json()['user']['phone']!r}"


def test_profile_update_name_only_does_not_touch_phone():
    _, token, _ = _register_user()
    # Set phone
    session.post(
        f"{BASE_URL}/api/me/profile",
        json={"phone": "+14165550111"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    # Update only name (phone omitted entirely)
    r = session.post(
        f"{BASE_URL}/api/me/profile",
        json={"name": "Just Name"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["name"] == "Just Name"
    assert body["user"]["phone"] == "+14165550111", "phone should be untouched when omitted"


def test_profile_update_empty_body_keeps_current():
    _, token, u = _register_user()
    r = session.post(
        f"{BASE_URL}/api/me/profile",
        json={},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == u["email"]


# ---------------- Welcome email trigger ----------------

def test_register_still_returns_ok_with_welcome_email_task():
    """Register must succeed and return a session token even though a best-effort
    welcome email task is scheduled. Coupon may or may not exist — either way,
    /auth/register response must not error out."""
    email = f"TEST_iter9_welcome_{uuid.uuid4().hex[:10]}@example.com"
    r = session.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": "TestPass123!", "name": "Welcome Tester"},
        timeout=15,
    )
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    body = r.json()
    assert "session_token" in body and body["session_token"].startswith("pw-")
    assert body["user"]["email"] == email.lower()

    # Give the asyncio task a moment to fire (best-effort; we only care that
    # register response is intact).
    time.sleep(1.0)

    # Follow-up /auth/me must work — proves session token is valid + user persisted.
    me = session.get(
        f"{BASE_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {body['session_token']}"},
        timeout=10,
    )
    assert me.status_code == 200
    assert me.json()["email"] == email.lower()


def test_register_duplicate_still_409_no_email_side_effects():
    email = f"TEST_iter9_dup_{uuid.uuid4().hex[:10]}@example.com"
    r1 = session.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": "TestPass123!"},
        timeout=15,
    )
    assert r1.status_code == 200
    r2 = session.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": "TestPass123!"},
        timeout=15,
    )
    assert r2.status_code == 409


# ---------------- Cleanup ----------------

def test_zzz_cleanup():
    """Remove TEST_iter9_* accounts we created."""
    from motor.motor_asyncio import AsyncIOMotorClient
    import asyncio

    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "bonghneshel_db")

    async def _run():
        c = AsyncIOMotorClient(mongo_url)
        d = c[db_name]
        # find test users
        cursor = d.users.find({"email": {"$regex": "^TEST_iter9_"}}, {"user_id": 1, "_id": 0})
        uids = [doc["user_id"] async for doc in cursor]
        if uids:
            await d.user_sessions.delete_many({"user_id": {"$in": uids}})
            await d.users.delete_many({"user_id": {"$in": uids}})
        c.close()

    try:
        asyncio.run(_run())
    except Exception as e:
        print(f"cleanup warning: {e}")
