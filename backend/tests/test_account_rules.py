"""A Manager manages the lower roles; only an Owner creates or changes Managers and Owners."""
import pytest

from tests.conftest import auth_headers, register_and_login


def _new_account(role: str, email: str) -> dict:
    return {"name": "New Person", "email": email, "password": "Password123!", "role": role}


def test_a_manager_can_create_every_role_below_manager(client):
    manager = register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")
    for i, role in enumerate(
        ["Kitchen Staff", "Inventory Staff", "Shift Supervisor", "Procurement Officer", "Delivery/Logistics Staff"]
    ):
        resp = client.post("/users", json=_new_account(role, f"p{i}@restaurant.com"), headers=auth_headers(manager))
        assert resp.status_code == 201, role


@pytest.mark.parametrize("role", ["Restaurant Manager", "Restaurant Owner"])
def test_a_manager_cannot_create_a_manager_or_owner(client, role):
    manager = register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")
    resp = client.post("/users", json=_new_account(role, "boss@restaurant.com"), headers=auth_headers(manager))
    assert resp.status_code == 403
    assert "Owner" in resp.json()["detail"]


@pytest.mark.parametrize("role", ["Restaurant Manager", "Restaurant Owner", "Kitchen Staff"])
def test_an_owner_can_create_any_role(client, role):
    owner = register_and_login(client, email="owner@restaurant.com", role="Restaurant Owner")
    resp = client.post("/users", json=_new_account(role, "someone@restaurant.com"), headers=auth_headers(owner))
    assert resp.status_code == 201


def test_a_manager_cannot_promote_someone_to_manager_or_owner(client):
    manager = register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")
    cook = client.post(
        "/users", json=_new_account("Kitchen Staff", "cook@restaurant.com"), headers=auth_headers(manager)
    ).json()
    for role in ("Restaurant Manager", "Restaurant Owner"):
        resp = client.patch(f"/users/{cook['user_id']}", json={"role": role}, headers=auth_headers(manager))
        assert resp.status_code == 403
    # Moving between the lower roles is still fine.
    ok = client.patch(f"/users/{cook['user_id']}", json={"role": "Inventory Staff"}, headers=auth_headers(manager))
    assert ok.status_code == 200


def test_a_manager_cannot_change_or_deactivate_another_manager_or_an_owner(client):
    owner = register_and_login(client, email="owner@restaurant.com", role="Restaurant Owner")
    manager = register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")
    other = client.post(
        "/users", json=_new_account("Restaurant Manager", "second@restaurant.com"), headers=auth_headers(owner)
    ).json()
    owner_id = client.get("/users/me", headers=auth_headers(owner)).json()["user_id"]
    for target in (other["user_id"], owner_id):
        assert client.patch(f"/users/{target}", json={"is_active": False}, headers=auth_headers(manager)).status_code == 403
        assert client.patch(f"/users/{target}", json={"role": "Kitchen Staff"}, headers=auth_headers(manager)).status_code == 403


def test_an_owner_can_change_a_manager(client):
    owner = register_and_login(client, email="owner@restaurant.com", role="Restaurant Owner")
    other = client.post(
        "/users", json=_new_account("Restaurant Manager", "second@restaurant.com"), headers=auth_headers(owner)
    ).json()
    resp = client.patch(f"/users/{other['user_id']}", json={"is_active": False}, headers=auth_headers(owner))
    assert resp.status_code == 200 and resp.json()["is_active"] is False
