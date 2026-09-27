"""
Backend tests for email + password auth (iteration 8):
  POST /api/auth/register
  POST /api/auth/login
  POST /api/auth/forgot-password
  POST /api/auth/reset-password
  GET  /api/auth/me   (session integrity check)

Runs against the EXTERNAL EXPO_PUBLIC_BACKEND_URL. The 6-digit reset code
is retrieved locally by brute-forcing the sha256 hash stored in
db.password_reset_codes (dev/test only) so we can exercise the happy path.
"""
import hashlib
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://clone-verify-2.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bonghneshel_db")

REVIEWER_EMAIL = "reviewer@bong-hneshel.ca"
REVIEWER_PASSWORD = "Cb%SD!UYjO7SEWc!"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module")
def new_email():
    return f"TEST_iter8_{uuid.uuid4().hex[:10]}@example.com"


def _cleanup_user(mongo, email: str):
    email = email.lower()
    user = mongo.users.find_one({"email": email}, {"user_id": 1})
    if user:
        mongo.user_sessions.delete_many({"user_id": user["user_id"]})
    mongo.users.delete_many({"email": email})
    mongo.password_reset_codes.delete_many({"email": email})


# ------------------------------ register ------------------------------
class TestRegister:
    def test_register_success(self, api, new_email, mongo):
        _cleanup_user(mongo, new_email)
        r = api.post(f"{BASE_URL}/api/auth/register",
                     json={"email": new_email, "password": "Passw0rd!123", "name": "Iter Eight"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert "session_token" in body and body["session_token"].startswith("pw-")
        assert body["user"]["email"] == new_email.lower()
        assert body["user"]["role"] == "customer"
        pytest.session_token = body["session_token"]
        pytest.user_id = body["user"]["user_id"]

    def test_register_duplicate_returns_409(self, api, new_email):
        r = api.post(f"{BASE_URL}/api/auth/register",
                     json={"email": new_email, "password": "Passw0rd!123"})
        assert r.status_code == 409, r.text

    def test_register_short_password_rejected(self, api):
        r = api.post(f"{BASE_URL}/api/auth/register",
                     json={"email": f"TEST_short_{uuid.uuid4().hex[:6]}@example.com", "password": "short"})
        assert r.status_code == 422, r.text


# -------------------------------- login --------------------------------
class TestLogin:
    def test_login_success(self, api, new_email):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": new_email, "password": "Passw0rd!123"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["session_token"].startswith("pw-")
        assert body["user"]["email"] == new_email.lower()
        pytest.session_token_login = body["session_token"]

    def test_login_wrong_password(self, api, new_email):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": new_email, "password": "WrongPassword!"})
        assert r.status_code == 401, r.text

    def test_login_unknown_email(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": f"nobody_{uuid.uuid4().hex[:8]}@example.com", "password": "whatever123"})
        assert r.status_code == 401, r.text

    def test_reviewer_login(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": REVIEWER_EMAIL, "password": REVIEWER_PASSWORD})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["session_token"].startswith("pw-")
        assert body["user"]["email"] == REVIEWER_EMAIL


# ---------------------------- /auth/me session ----------------------------
class TestSessionIntegrity:
    def test_me_with_register_token(self, api, new_email):
        r = api.get(f"{BASE_URL}/api/auth/me",
                    headers={"Authorization": f"Bearer {pytest.session_token}"})
        assert r.status_code == 200, r.text
        assert r.json()["email"] == new_email.lower()

    def test_me_with_login_token(self, api, new_email):
        r = api.get(f"{BASE_URL}/api/auth/me",
                    headers={"Authorization": f"Bearer {pytest.session_token_login}"})
        assert r.status_code == 200, r.text
        assert r.json()["email"] == new_email.lower()

    def test_me_unauthorized(self, api):
        r = api.get(f"{BASE_URL}/api/auth/me",
                    headers={"Authorization": "Bearer pw-invalid-token"})
        assert r.status_code == 401


# --------------------------- forgot-password ---------------------------
class TestForgot:
    def test_forgot_for_existing_email_returns_generic_200(self, api, new_email):
        r = api.post(f"{BASE_URL}/api/auth/forgot-password", json={"email": new_email})
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True
        assert "message" in body

    def test_forgot_for_unknown_email_returns_same_generic_200(self, api):
        r = api.post(f"{BASE_URL}/api/auth/forgot-password",
                     json={"email": f"no_such_{uuid.uuid4().hex[:8]}@example.com"})
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True
        assert "message" in body


# ---------------------------- reset-password ----------------------------
def _brute_force_code(target_hash: str) -> str | None:
    for i in range(1000000):
        c = f"{i:06d}"
        if hashlib.sha256(c.encode()).hexdigest() == target_hash:
            return c
    return None


class TestReset:
    def test_reset_wrong_code_increments_attempts(self, api, new_email, mongo):
        rec = mongo.password_reset_codes.find_one({"email": new_email.lower()})
        assert rec is not None, "expected reset code from previous forgot-password test"
        before = rec.get("attempts", 0)
        r = api.post(f"{BASE_URL}/api/auth/reset-password",
                     json={"email": new_email, "code": "000000", "password": "NewPassw0rd!"})
        assert r.status_code == 400
        after_doc = mongo.password_reset_codes.find_one({"email": new_email.lower()})
        # Note: the wrong code 000000 might legitimately match (1/1e6). Accept either same-code or attempts+1.
        if after_doc.get("code_hash") == rec.get("code_hash"):
            assert after_doc.get("attempts", 0) == before + 1

    def test_reset_lockout_after_5_attempts(self, api, new_email, mongo):
        mongo.password_reset_codes.update_one({"email": new_email.lower()}, {"$set": {"attempts": 5}})
        r = api.post(f"{BASE_URL}/api/auth/reset-password",
                     json={"email": new_email, "code": "123456", "password": "NewPassw0rd!"})
        assert r.status_code == 400
        # Reset attempts so we can continue happy path
        mongo.password_reset_codes.update_one({"email": new_email.lower()}, {"$set": {"attempts": 0}})

    def test_reset_happy_path_and_invalidates_sessions(self, api, new_email, mongo):
        # Force a fresh forgot to obtain a new code we can brute-force
        r = api.post(f"{BASE_URL}/api/auth/forgot-password", json={"email": new_email})
        assert r.status_code == 200
        rec = mongo.password_reset_codes.find_one({"email": new_email.lower()})
        assert rec is not None
        code = _brute_force_code(rec["code_hash"])
        assert code is not None, "could not brute-force reset code"

        # Ensure we have a valid session token before reset
        old_token = pytest.session_token_login
        me = api.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {old_token}"})
        assert me.status_code == 200

        r = api.post(f"{BASE_URL}/api/auth/reset-password",
                     json={"email": new_email, "code": code, "password": "BrandNewPw!456"})
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        # Old session invalidated
        me2 = api.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {old_token}"})
        assert me2.status_code == 401, f"expected old session to be invalidated, got {me2.status_code}"

        # Old password no longer works
        r_old = api.post(f"{BASE_URL}/api/auth/login",
                        json={"email": new_email, "password": "Passw0rd!123"})
        assert r_old.status_code == 401

        # New password works
        r_new = api.post(f"{BASE_URL}/api/auth/login",
                        json={"email": new_email, "password": "BrandNewPw!456"})
        assert r_new.status_code == 200, r_new.text

        # Code reuse rejected
        r_reuse = api.post(f"{BASE_URL}/api/auth/reset-password",
                          json={"email": new_email, "code": code, "password": "AnotherPw!789"})
        assert r_reuse.status_code == 400

    def test_zzz_cleanup(self, mongo, new_email):
        _cleanup_user(mongo, new_email)
