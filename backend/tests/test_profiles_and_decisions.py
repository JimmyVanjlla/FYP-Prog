"""Supervisor feedback, server side:
- staff accounts carry contact details; people can view and edit their own
  profile (but not their role) and change their password;
- rejecting a purchase order or portion review needs a reason, which is kept,
  along with who decided and when, for the approvals history.
"""
from datetime import date, timedelta
from decimal import Decimal

from app.models.feedback import PortionRecommendation
from app.models.menu import MenuItem
from tests.conftest import auth_headers, register_and_login

DETAILS = {
    "phone_number": "+60 12-345 6789",
    "address": "12 Jalan Bukit, Kuala Lumpur",
    "emergency_contact_name": "Mei Tan",
    "emergency_contact_phone": "+60 13-987 6543",
}


def _manager(client):
    return auth_headers(register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager"))


class TestStaffDetails:
    def test_an_account_can_be_created_with_contact_details(self, client):
        manager = _manager(client)
        body = {"name": "Aisha", "email": "aisha@restaurant.com", "password": "password123", "role": "Kitchen Staff", **DETAILS}

        created = client.post("/users", json=body, headers=manager)

        assert created.status_code == 201
        for key, value in DETAILS.items():
            assert created.json()[key] == value
        assert client.get("/users", headers=manager).json()[0].keys() >= DETAILS.keys()

    def test_the_details_are_optional(self, client):
        manager = _manager(client)
        created = client.post(
            "/users",
            json={"name": "Bob", "email": "bob@restaurant.com", "password": "password123", "role": "Kitchen Staff"},
            headers=manager,
        )
        assert created.status_code == 201
        assert created.json()["phone_number"] is None and created.json()["address"] is None

    def test_a_manager_can_correct_a_staff_members_details(self, client):
        manager = _manager(client)
        staff = client.post(
            "/users",
            json={"name": "Cara", "email": "cara@restaurant.com", "password": "password123", "role": "Kitchen Staff"},
            headers=manager,
        ).json()

        resp = client.patch(f"/users/{staff['user_id']}", json={"name": "Cara Lim", **DETAILS}, headers=manager)

        assert resp.status_code == 200
        assert resp.json()["name"] == "Cara Lim" and resp.json()["phone_number"] == DETAILS["phone_number"]

    def test_sending_null_for_a_required_field_changes_nothing(self, client):
        manager = _manager(client)
        staff = client.post(
            "/users",
            json={"name": "Dev", "email": "dev@restaurant.com", "password": "password123", "role": "Kitchen Staff"},
            headers=manager,
        ).json()
        resp = client.patch(f"/users/{staff['user_id']}", json={"name": None, "role": None, "is_active": None}, headers=manager)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Dev" and resp.json()["role"] == "Kitchen Staff" and resp.json()["is_active"] is True

    def test_a_phone_number_must_look_like_one(self, client):
        manager = _manager(client)
        body = {"name": "Eve", "email": "eve@restaurant.com", "password": "password123", "role": "Kitchen Staff"}
        for bad in ("hello", "12", "+60 12 abc 456"):
            assert client.post("/users", json={**body, "phone_number": bad}, headers=manager).status_code == 422


class TestOwnProfile:
    def test_anyone_can_view_and_edit_their_own_details(self, client):
        token = register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff")
        me = auth_headers(token)

        resp = client.patch("/users/me", json={"name": "Kay Kitchen", **DETAILS}, headers=me)

        assert resp.status_code == 200
        shown = client.get("/users/me", headers=me).json()
        assert shown["name"] == "Kay Kitchen" and shown["address"] == DETAILS["address"]
        assert shown["role"] == "Kitchen Staff" and shown["email"] == "kitchen@restaurant.com"

    def test_nobody_can_change_their_own_role_or_active_status_or_email(self, client):
        me = auth_headers(register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff"))

        resp = client.patch(
            "/users/me",
            json={"role": "Restaurant Manager", "is_active": False, "email": "boss@restaurant.com"},
            headers=me,
        )

        assert resp.status_code == 200  # unknown fields are ignored, not applied
        shown = client.get("/users/me", headers=me).json()
        assert shown["role"] == "Kitchen Staff" and shown["is_active"] is True and shown["email"] == "kitchen@restaurant.com"
        assert client.get("/users", headers=me).status_code == 403  # and it still isn't a manager

    def test_a_detail_can_be_cleared(self, client):
        me = auth_headers(register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff"))
        client.patch("/users/me", json=DETAILS, headers=me)

        resp = client.patch("/users/me", json={"address": "", "phone_number": "  "}, headers=me)

        assert resp.json()["address"] is None and resp.json()["phone_number"] is None
        assert resp.json()["emergency_contact_name"] == DETAILS["emergency_contact_name"]  # untouched

    def test_the_name_cannot_be_blanked(self, client):
        me = auth_headers(register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff"))
        assert client.patch("/users/me", json={"name": ""}, headers=me).status_code == 422

    def test_profile_routes_need_a_login(self, client):
        assert client.patch("/users/me", json={"name": "x"}).status_code == 401
        assert client.post("/users/me/password", json={"current_password": "a", "new_password": "bbbbbbbb"}).status_code == 401


class TestPasswordChange:
    def test_changing_it_needs_the_current_one_and_takes_effect(self, client):
        email = "kitchen@restaurant.com"
        me = auth_headers(register_and_login(client, email=email, role="Kitchen Staff", password="oldpassword1"))

        wrong = client.post("/users/me/password", json={"current_password": "nope-nope", "new_password": "newpassword1"}, headers=me)
        assert wrong.status_code == 400 and "current password" in wrong.json()["detail"]

        ok = client.post("/users/me/password", json={"current_password": "oldpassword1", "new_password": "newpassword1"}, headers=me)
        assert ok.status_code == 204

        assert client.post("/auth/login", json={"email": email, "password": "oldpassword1"}).status_code == 401
        assert client.post("/auth/login", json={"email": email, "password": "newpassword1"}).status_code == 200

    def test_a_short_new_password_is_refused(self, client):
        me = auth_headers(register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff", password="oldpassword1"))
        resp = client.post("/users/me/password", json={"current_password": "oldpassword1", "new_password": "short"}, headers=me)
        assert resp.status_code == 422


def _purchase_order(client):
    manager = _manager(client)
    officer = auth_headers(register_and_login(client, email="po@restaurant.com", role="Procurement Officer"))
    inventory = auth_headers(register_and_login(client, email="inv@restaurant.com", role="Inventory Staff"))
    rice = client.post("/inventory/ingredients", json={"name": "Rice", "unit": "kg", "current_stock": "1"}, headers=inventory).json()
    supplier = client.post("/procurement/suppliers", json={"name": "Cheap Co", "contact_info": "1"}, headers=officer).json()
    client.post(
        "/procurement/suppliers/pricing",
        json={"supplier_id": supplier["supplier_id"], "ingredient_id": rice["ingredient_id"], "unit_price": "2.00"},
        headers=officer,
    ).raise_for_status()
    po = client.post(
        "/procurement/purchase-orders",
        json={"supplier_id": supplier["supplier_id"], "line_items": [{"ingredient_id": rice["ingredient_id"], "quantity": "10"}]},
        headers=officer,
    ).json()
    return manager, officer, po


class TestPurchaseOrderDecisions:
    def test_a_rejection_needs_a_reason(self, client):
        manager, _officer, po = _purchase_order(client)
        for body in ({}, {"reason": ""}, {"reason": "no"}, {"reason": "   "}):
            assert client.post(f"/procurement/purchase-orders/{po['po_id']}/reject", json=body, headers=manager).status_code == 422
        assert client.get("/procurement/purchase-orders", headers=manager).json()[0]["status"] == "pending_approval"

    def test_the_reason_who_and_when_are_kept_and_the_officer_is_told(self, client):
        manager, officer, po = _purchase_order(client)

        resp = client.post(
            f"/procurement/purchase-orders/{po['po_id']}/reject",
            json={"reason": "  Over this month's budget  "},
            headers=manager,
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "rejected" and body["decision_note"] == "Over this month's budget"
        assert body["decided_by"] is not None and body["decided_at"] is not None
        inbox = client.get("/kitchen/notifications", headers=officer).json()
        assert any("rejected" in n["message"] and "Over this month's budget" in n["message"] for n in inbox)

    def test_an_approval_records_who_and_when(self, client):
        manager, _officer, po = _purchase_order(client)
        body = client.post(f"/procurement/purchase-orders/{po['po_id']}/approve", headers=manager).json()
        assert body["status"] == "approved"
        assert body["decided_by"] == body["approved_by"] and body["decided_at"] is not None and body["decision_note"] is None

    def test_a_decision_is_final(self, client):
        manager, _officer, po = _purchase_order(client)
        url = f"/procurement/purchase-orders/{po['po_id']}"
        client.post(f"{url}/reject", json={"reason": "Too expensive"}, headers=manager)

        assert client.post(f"{url}/approve", headers=manager).status_code == 409
        assert client.post(f"{url}/reject", json={"reason": "Again please"}, headers=manager).status_code == 409
        assert client.get("/procurement/purchase-orders", headers=manager).json()[0]["status"] == "rejected"

    def test_an_approved_order_cannot_then_be_rejected(self, client):
        manager, _officer, po = _purchase_order(client)
        url = f"/procurement/purchase-orders/{po['po_id']}"
        client.post(f"{url}/approve", headers=manager)
        assert client.post(f"{url}/reject", json={"reason": "Changed my mind"}, headers=manager).status_code == 409

    def test_unknown_order_is_404(self, client):
        manager = _manager(client)
        assert client.post("/procurement/purchase-orders/999/reject", json={"reason": "Not there"}, headers=manager).status_code == 404

    def test_only_a_manager_decides(self, client):
        _manager_headers, officer, po = _purchase_order(client)
        url = f"/procurement/purchase-orders/{po['po_id']}"
        assert client.post(f"{url}/approve", headers=officer).status_code == 403
        assert client.post(f"{url}/reject", json={"reason": "Not allowed"}, headers=officer).status_code == 403


def _portion_review(client, db_session):
    manager = _manager(client)
    item = client.post("/menu-items", json={"name": "Curry Laksa", "price": "9.00", "category": "Noodles"}, headers=manager).json()
    review = PortionRecommendation(
        menu_item_id=item["menu_item_id"], leftover_rate=Decimal("32.00"), suggested_portion_size=Decimal("0.180")
    )
    db_session.add(review)
    db_session.commit()
    return manager, review.recommendation_id


class TestPortionReviewDecisions:
    def test_a_rejection_needs_a_reason_and_keeps_it(self, client, db_session):
        manager, rid = _portion_review(client, db_session)
        url = f"/portion-feedback/recommendations/{rid}/reject"

        assert client.post(url, json={}, headers=manager).status_code == 422
        resp = client.post(url, json={"reason": "Customers like the big portion"}, headers=manager)

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "rejected" and body["decision_note"] == "Customers like the big portion"
        assert body["decided_by"] is not None and body["decided_at"] is not None

    def test_an_approval_records_who_and_when(self, client, db_session):
        manager, rid = _portion_review(client, db_session)
        body = client.post(f"/portion-feedback/recommendations/{rid}/approve", headers=manager).json()
        assert body["status"] == "approved" and body["decided_by"] is not None and body["decided_at"] is not None

    def test_a_decided_review_cannot_be_flipped(self, client, db_session):
        manager, rid = _portion_review(client, db_session)
        client.post(f"/portion-feedback/recommendations/{rid}/approve", headers=manager)
        resp = client.post(f"/portion-feedback/recommendations/{rid}/reject", json={"reason": "Too late now"}, headers=manager)
        assert resp.status_code == 422

    def test_history_is_available_through_the_status_filter(self, client, db_session):
        manager, rid = _portion_review(client, db_session)
        client.post(f"/portion-feedback/recommendations/{rid}/reject", json={"reason": "Keep the portion"}, headers=manager)
        assert client.get("/portion-feedback/recommendations?status_filter=pending", headers=manager).json() == []
        rejected = client.get("/portion-feedback/recommendations?status_filter=rejected", headers=manager).json()
        assert [r["recommendation_id"] for r in rejected] == [rid]
