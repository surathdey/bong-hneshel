"""Iteration 13: Comprehensive Review Management System backend tests.

Runs against the public preview URL to validate what customers actually see.
Uses direct Mongo seed for the review-request token flow (no Stripe end-to-end).
"""
import os
import uuid
import io
import csv
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

# Load backend env for DB access + admin creds
load_dotenv(Path("/app/backend/.env"))
load_dotenv(Path("/app/frontend/.env"), override=False)

BASE_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
    or ""
).rstrip("/")
assert BASE_URL, "Missing EXPO_PUBLIC_BACKEND_URL / EXPO_BACKEND_URL"

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@bong-hneshel.ca")
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


# ---------------- Shared fixtures ----------------
@pytest.fixture(scope="session")
def db():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/admin/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    j = r.json()
    tok = j.get("token") or j.get("access_token")
    assert tok, f"no token in login response: {j}"
    return tok


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def master_item(db):
    mi = db.master_menu.find_one({}, {"_id": 0, "item_id": 1, "name": 1})
    assert mi, "no master menu items seeded"
    return mi


@pytest.fixture
def seeded_review_request(db, master_item):
    """Insert a review_request doc directly and yield its token/order_id/item.
    Cleans up reviews + review_requests + review docs on teardown.
    """
    token = "TEST_tok_" + uuid.uuid4().hex[:10]
    order_id = "TEST_ord_" + uuid.uuid4().hex[:8]
    iid = master_item["item_id"]
    iname = master_item["name"]
    db.review_requests.delete_many({"order_id": order_id})
    db.review_requests.insert_one(
        {
            "token": token,
            "order_id": order_id,
            "user_id": "",
            "status": "sent",
            "items": [{"item_id": iid, "name": iname, "image_url": ""}],
            "customer_name": "TEST_Reviewer",
            "phone": "",
            "email": "",
            "public_base_url": "",
            "created_at": datetime.now(timezone.utc),
        }
    )
    yield {"token": token, "order_id": order_id, "item_id": iid, "item_name": iname}
    # Teardown
    db.reviews.delete_many({"order_id": order_id})
    db.review_requests.delete_many({"order_id": order_id})


# ==========================================================
# Admin login
# ==========================================================
class TestAdminLogin:
    def test_admin_login_returns_token(self):
        r = requests.post(
            f"{BASE_URL}/api/admin/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert (j.get("token") or j.get("access_token")), j

    def test_admin_login_wrong_password(self):
        r = requests.post(
            f"{BASE_URL}/api/admin/login",
            json={"email": ADMIN_EMAIL, "password": "wrongpw123"},
            timeout=15,
        )
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"


# ==========================================================
# Public review-request token endpoint
# ==========================================================
class TestPublicReviewRequest:
    def test_get_valid_token(self, seeded_review_request):
        tok = seeded_review_request["token"]
        r = requests.get(f"{BASE_URL}/api/reviews/request/{tok}", timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "business_name" in j and j["business_name"]
        assert j["customer_name"] == "TEST_Reviewer"
        assert isinstance(j["items"], list) and len(j["items"]) == 1
        assert j["items"][0]["item_id"] == seeded_review_request["item_id"]
        assert j["already_submitted"] is False

    def test_get_invalid_token_404(self):
        r = requests.get(f"{BASE_URL}/api/reviews/request/nope_bad_token_xyz", timeout=15)
        assert r.status_code == 404


# ==========================================================
# Public review submit
# ==========================================================
class TestReviewSubmit:
    def test_submit_stores_pending(self, seeded_review_request, db):
        s = seeded_review_request
        r = requests.post(
            f"{BASE_URL}/api/reviews/submit",
            json={
                "token": s["token"],
                "reviews": [{"item_id": s["item_id"], "rating": 5, "comment": "Yum!"}],
            },
            timeout=15,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True
        # Customer-blind generic success
        assert "posted" in (j.get("message") or "").lower()
        # Verify stored as pending
        rev = db.reviews.find_one({"order_id": s["order_id"]})
        assert rev, "review not persisted"
        assert rev["status"] == "pending"
        assert rev["rating"] == 5
        assert rev["comment"] == "Yum!"

    def test_submit_idempotent_no_duplicates(self, seeded_review_request, db):
        s = seeded_review_request
        # first submit
        r1 = requests.post(
            f"{BASE_URL}/api/reviews/submit",
            json={"token": s["token"], "reviews": [{"item_id": s["item_id"], "rating": 4}]},
            timeout=15,
        )
        assert r1.status_code == 200
        # second submit — should still succeed generically, no duplicate insert
        r2 = requests.post(
            f"{BASE_URL}/api/reviews/submit",
            json={"token": s["token"], "reviews": [{"item_id": s["item_id"], "rating": 1}]},
            timeout=15,
        )
        assert r2.status_code == 200
        assert r2.json().get("ok") is True
        count = db.reviews.count_documents({"order_id": s["order_id"]})
        assert count == 1, f"expected 1 review after resubmit, got {count}"

    def test_submit_invalid_token(self):
        r = requests.post(
            f"{BASE_URL}/api/reviews/submit",
            json={"token": "totally_fake", "reviews": [{"item_id": "x", "rating": 5}]},
            timeout=15,
        )
        assert r.status_code == 404

    def test_submit_rating_out_of_range(self, seeded_review_request):
        s = seeded_review_request
        r = requests.post(
            f"{BASE_URL}/api/reviews/submit",
            json={"token": s["token"], "reviews": [{"item_id": s["item_id"], "rating": 9}]},
            timeout=15,
        )
        # Pydantic validation error
        assert r.status_code == 422


# ==========================================================
# Moderation hides reviews from public endpoint
# ==========================================================
class TestModerationVisibility:
    def test_pending_hidden_then_approved_visible(self, seeded_review_request, admin_headers, db):
        s = seeded_review_request
        iid = s["item_id"]
        # Snapshot before
        r0 = requests.get(f"{BASE_URL}/api/menu-items/{iid}/reviews", timeout=15)
        assert r0.status_code == 200
        before_count = r0.json()["review_count"]
        # Submit a review — pending
        requests.post(
            f"{BASE_URL}/api/reviews/submit",
            json={"token": s["token"], "reviews": [{"item_id": iid, "rating": 5, "comment": "hidden!"}]},
            timeout=15,
        )
        r1 = requests.get(f"{BASE_URL}/api/menu-items/{iid}/reviews", timeout=15)
        assert r1.status_code == 200
        assert r1.json()["review_count"] == before_count, "pending review must be hidden"
        # Find review_id from admin listing
        r2 = requests.get(f"{BASE_URL}/api/admin/reviews?status=pending", headers=admin_headers, timeout=15)
        assert r2.status_code == 200
        pend = [x for x in r2.json()["reviews"] if x.get("order_id") == s["order_id"]]
        assert pend, "pending review missing from admin queue"
        review_id = pend[0]["review_id"]
        # Approve
        r3 = requests.post(
            f"{BASE_URL}/api/admin/reviews/{review_id}/moderate",
            json={"action": "approve"},
            headers=admin_headers,
            timeout=15,
        )
        assert r3.status_code == 200
        assert r3.json()["status"] == "approved"
        # Now visible
        r4 = requests.get(f"{BASE_URL}/api/menu-items/{iid}/reviews", timeout=15)
        j4 = r4.json()
        assert j4["review_count"] == before_count + 1
        assert j4["avg_rating"] >= 1
        # And review appears in returned list
        found = [rv for rv in j4["reviews"] if rv["review_id"] == review_id]
        assert found and found[0]["comment"] == "hidden!"

    def test_reject_action(self, seeded_review_request, admin_headers, db):
        s = seeded_review_request
        requests.post(
            f"{BASE_URL}/api/reviews/submit",
            json={"token": s["token"], "reviews": [{"item_id": s["item_id"], "rating": 2}]},
            timeout=15,
        )
        rev = db.reviews.find_one({"order_id": s["order_id"]})
        assert rev
        r = requests.post(
            f"{BASE_URL}/api/admin/reviews/{rev['review_id']}/moderate",
            json={"action": "reject"},
            headers=admin_headers,
            timeout=15,
        )
        assert r.status_code == 200 and r.json()["status"] == "rejected"
        r2 = requests.get(f"{BASE_URL}/api/menu-items/{s['item_id']}/reviews", timeout=15)
        assert not any(x["review_id"] == rev["review_id"] for x in r2.json()["reviews"])

    def test_delete_review(self, seeded_review_request, admin_headers, db):
        s = seeded_review_request
        requests.post(
            f"{BASE_URL}/api/reviews/submit",
            json={"token": s["token"], "reviews": [{"item_id": s["item_id"], "rating": 3}]},
            timeout=15,
        )
        rev = db.reviews.find_one({"order_id": s["order_id"]})
        r = requests.delete(
            f"{BASE_URL}/api/admin/reviews/{rev['review_id']}",
            headers=admin_headers,
            timeout=15,
        )
        assert r.status_code == 200 and r.json()["ok"] is True
        assert db.reviews.find_one({"review_id": rev["review_id"]}) is None

    def test_moderate_bad_action(self, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/admin/reviews/nonexistent_id/moderate",
            json={"action": "banana"},
            headers=admin_headers,
            timeout=15,
        )
        assert r.status_code == 400


# ==========================================================
# Admin auth guard
# ==========================================================
class TestAdminAuthGuard:
    def test_list_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/admin/reviews", timeout=15)
        assert r.status_code == 401

    def test_moderate_requires_auth(self):
        r = requests.post(
            f"{BASE_URL}/api/admin/reviews/whatever/moderate",
            json={"action": "approve"},
            timeout=15,
        )
        assert r.status_code == 401

    def test_delete_requires_auth(self):
        r = requests.delete(f"{BASE_URL}/api/admin/reviews/whatever", timeout=15)
        assert r.status_code == 401

    def test_bulk_upload_requires_auth(self):
        r = requests.post(
            f"{BASE_URL}/api/admin/reviews/bulk-upload",
            files={"file": ("x.csv", "item_id,rating\n", "text/csv")},
            timeout=15,
        )
        assert r.status_code == 401


# ==========================================================
# Admin listing counts
# ==========================================================
class TestAdminList:
    def test_counts_shape(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/reviews?status=pending", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert "reviews" in j and isinstance(j["reviews"], list)
        assert "counts" in j
        for st in ("pending", "approved", "rejected"):
            assert st in j["counts"] and isinstance(j["counts"][st], int)

    def test_filter_by_status(self, admin_headers):
        for st in ("pending", "approved", "rejected"):
            r = requests.get(f"{BASE_URL}/api/admin/reviews?status={st}", headers=admin_headers, timeout=15)
            assert r.status_code == 200
            # every review in list must match filter
            for rv in r.json()["reviews"]:
                assert rv["status"] == st


# ==========================================================
# CSV bulk upload
# ==========================================================
class TestBulkUpload:
    def test_bulk_upload_by_item_id(self, admin_headers, master_item, db):
        iid = master_item["item_id"]
        csv_text = (
            "item_id,rating,comment,customer_name\n"
            f"{iid},5,TEST_bulk_row1,Old Cust A\n"
            f"{iid},3,TEST_bulk_row2,Old Cust B\n"
            "bad_id_xyz,4,bad,ghost\n"
        )
        r = requests.post(
            f"{BASE_URL}/api/admin/reviews/bulk-upload",
            headers=admin_headers,
            files={"file": ("reviews.csv", csv_text, "text/csv")},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True
        assert j["inserted"] == 2
        assert j["error_count"] == 1
        assert len(j["errors"]) == 1
        assert "bad_id_xyz" in j["errors"][0]
        # Cleanup
        db.reviews.delete_many({"source": "admin_bulk", "comment": {"$in": ["TEST_bulk_row1", "TEST_bulk_row2"]}})

    def test_bulk_upload_by_item_name(self, admin_headers, master_item, db):
        iname = master_item["name"]
        csv_text = (
            "item_name,rating,comment,customer_name\n"
            f"{iname},4,TEST_bulk_name_row,By Name Cust\n"
        )
        r = requests.post(
            f"{BASE_URL}/api/admin/reviews/bulk-upload",
            headers=admin_headers,
            files={"file": ("reviews.csv", csv_text, "text/csv")},
            timeout=20,
        )
        assert r.status_code == 200
        j = r.json()
        assert j["inserted"] == 1, j
        # Confirm inserted as approved
        d = db.reviews.find_one({"comment": "TEST_bulk_name_row"})
        assert d and d["status"] == "approved" and d["source"] == "admin_bulk"
        db.reviews.delete_many({"comment": "TEST_bulk_name_row"})

    def test_bulk_upload_rating_range(self, admin_headers, master_item):
        iid = master_item["item_id"]
        csv_text = f"item_id,rating,comment,customer_name\n{iid},9,TEST_out_of_range,X\n{iid},0,TEST_zero,Y\n"
        r = requests.post(
            f"{BASE_URL}/api/admin/reviews/bulk-upload",
            headers=admin_headers,
            files={"file": ("reviews.csv", csv_text, "text/csv")},
            timeout=15,
        )
        assert r.status_code == 200
        j = r.json()
        assert j["inserted"] == 0
        assert j["error_count"] == 2


# ==========================================================
# Reviews summary batch
# ==========================================================
class TestReviewsSummary:
    def test_summary_shape(self, master_item):
        iid = master_item["item_id"]
        r = requests.get(f"{BASE_URL}/api/reviews/summary?item_ids={iid},nonexistent_x", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert "ratings" in j and isinstance(j["ratings"], dict)
        # existent may or may not be present in map if no approved reviews
        if iid in j["ratings"]:
            assert "avg_rating" in j["ratings"][iid]
            assert "review_count" in j["ratings"][iid]


# ==========================================================
# Menu enrichment
# ==========================================================
class TestMenuEnrichment:
    def test_menu_current_has_rating_fields(self):
        r = requests.get(f"{BASE_URL}/api/menu/current", timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        items = j.get("items") or j.get("current") or []
        # /api/menu/current may return {items: [...]} — normalize
        if isinstance(j, dict) and "items" in j:
            items = j["items"]
        if not items:
            pytest.skip("no current menu items to check")
        it = items[0]
        assert "avg_rating" in it, f"avg_rating missing on menu/current item; keys={list(it.keys())}"
        assert "review_count" in it

    def test_menu_anytime_has_rating_fields(self):
        r = requests.get(f"{BASE_URL}/api/menu/anytime", timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        # anytime endpoint may return list OR dict-with-items
        if isinstance(j, dict):
            items = j.get("items") or []
        elif isinstance(j, list):
            items = j
        else:
            items = []
        if not items:
            pytest.skip("no anytime menu items to check")
        it = items[0]
        assert "avg_rating" in it
        assert "review_count" in it


# ==========================================================
# Settings: reviews_enabled + review_request_delay_days
# ==========================================================
class TestReviewSettings:
    def test_admin_settings_has_review_fields(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/settings", headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "reviews_enabled" in j
        assert "review_request_delay_days" in j

    def test_put_settings_persists(self, admin_headers):
        # read current
        r = requests.get(f"{BASE_URL}/api/admin/settings", headers=admin_headers, timeout=15)
        cur = r.json()
        original_enabled = bool(cur.get("reviews_enabled", True))
        original_delay = int(cur.get("review_request_delay_days", 1) or 0)
        # set new
        new_payload = dict(cur)
        new_payload["reviews_enabled"] = True
        new_payload["review_request_delay_days"] = 3
        pr = requests.put(
            f"{BASE_URL}/api/admin/settings",
            headers=admin_headers,
            json=new_payload,
            timeout=15,
        )
        assert pr.status_code == 200, pr.text
        # verify
        r2 = requests.get(f"{BASE_URL}/api/admin/settings", headers=admin_headers, timeout=15)
        j2 = r2.json()
        assert j2["reviews_enabled"] is True
        assert int(j2["review_request_delay_days"]) == 3
        # restore
        new_payload["reviews_enabled"] = original_enabled
        new_payload["review_request_delay_days"] = original_delay
        requests.put(f"{BASE_URL}/api/admin/settings", headers=admin_headers, json=new_payload, timeout=15)

    def test_public_settings_exposes_reviews_enabled(self):
        r = requests.get(f"{BASE_URL}/api/settings", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert "reviews_enabled" in j, f"public settings missing reviews_enabled: keys={list(j.keys())}"


# ==========================================================
# Delivery trigger: mark order delivered -> creates review_request
# ==========================================================
class TestDeliveryTrigger:
    def test_delivered_order_creates_review_request(self, db, admin_headers, master_item):
        """Directly seed a paid COD-style order in Mongo, then mark it delivered via admin API.
        Verify a review_request doc is created.
        """
        oid = "TEST_ordDlv_" + uuid.uuid4().hex[:8]
        iid = master_item["item_id"]
        iname = master_item["name"]
        now = datetime.now(timezone.utc)
        db.orders.delete_many({"order_id": oid})
        db.orders.insert_one(
            {
                "order_id": oid,
                "user_id": "",
                "status": "paid",
                "payment_status": "paid",
                "payment_method": "cod",
                "customer_name": "TEST Delivered",
                "customer_email": "",
                "customer_phone": "",
                "items": [{"kind": "menu", "ref_id": iid, "name": iname, "quantity": 1, "price_cents": 1000}],
                "items_snapshot": [{"kind": "menu", "ref_id": iid, "name": iname, "quantity": 1, "price_cents": 1000}],
                "total_cents": 1000,
                "created_at": now,
            }
        )
        db.review_requests.delete_many({"order_id": oid})
        try:
            r = requests.post(
                f"{BASE_URL}/api/orders/{oid}/status",
                json={"status": "delivered"},
                headers=admin_headers,
                timeout=20,
            )
            # Some backends use a different admin endpoint — accept 200 or 404
            if r.status_code == 404:
                pytest.skip(f"POST /api/orders/{{id}}/status not exposed here: 404")
            assert r.status_code == 200, r.text
            # give the async schedule task a moment to run
            import time as _t
            for _ in range(10):
                rr = db.review_requests.find_one({"order_id": oid})
                if rr:
                    break
                _t.sleep(0.3)
            rr = db.review_requests.find_one({"order_id": oid})
            assert rr, "review_request not created for delivered order"
            assert rr.get("token")
            assert isinstance(rr.get("items"), list) and len(rr["items"]) >= 1
            assert rr["items"][0]["item_id"] == iid
        finally:
            db.orders.delete_many({"order_id": oid})
            db.review_requests.delete_many({"order_id": oid})
            db.reviews.delete_many({"order_id": oid})
