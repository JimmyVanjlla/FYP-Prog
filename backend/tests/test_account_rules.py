"""The Manager is the only role that manages accounts, and can create any of the three roles."""
import pytest

from tests.conftest import auth_headers, register_and_login


def _new_account(role: str, email: str) -> dict:
    return {"name": "New Person", "email": email, "password": "Password123!", "role": role}


@pytest.mark.parametrize("role", ["Restaurant Manager", "Shift Supervisor", "Kitchen Staff"])
def test_a_manager_can_create_every_role(client, role):
    manager = register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")
    resp = client.post("/users", json=_new_account(role, "someone@restaurant.com"), headers=auth_headers(manager))
    assert resp.status_code == 201


@pytest.mark.parametrize("role", ["Restaurant Owner", "Inventory Staff", "Procurement Officer", "Delivery/Logistics Staff"])
def test_the_removed_roles_cannot_be_created(client, role):
    manager = register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")
    resp = client.post("/users", json=_new_account(role, "old@restaurant.com"), headers=auth_headers(manager))
    assert resp.status_code == 422


def test_only_a_manager_manages_accounts(client):
    manager = register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")
    for i, role in enumerate(["Shift Supervisor", "Kitchen Staff"]):
        client.post("/users", json=_new_account(role, f"p{i}@restaurant.com"), headers=auth_headers(manager))
    for i in range(2):
        token = client.post("/auth/login", json={"email": f"p{i}@restaurant.com", "password": "Password123!"}).json()[
            "access_token"
        ]
        assert client.get("/users", headers=auth_headers(token)).status_code == 403
        assert client.post("/users", json=_new_account("Kitchen Staff", "x@restaurant.com"), headers=auth_headers(token)).status_code == 403


def test_a_manager_can_change_the_role_of_anyone_including_another_manager(client):
    manager = register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager")
    other = client.post(
        "/users", json=_new_account("Restaurant Manager", "second@restaurant.com"), headers=auth_headers(manager)
    ).json()
    cook = client.post(
        "/users", json=_new_account("Kitchen Staff", "cook@restaurant.com"), headers=auth_headers(manager)
    ).json()
    assert client.patch(f"/users/{cook['user_id']}", json={"role": "Shift Supervisor"}, headers=auth_headers(manager)).status_code == 200
    resp = client.patch(f"/users/{other['user_id']}", json={"is_active": False}, headers=auth_headers(manager))
    assert resp.status_code == 200 and resp.json()["is_active"] is False
