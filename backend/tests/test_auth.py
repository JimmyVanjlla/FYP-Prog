from tests.conftest import auth_headers, register_and_login


def test_register_creates_user(client):
    resp = client.post(
        "/auth/register",
        json={
            "name": "Jane Tan",
            "email": "jane.tan@restaurant.com",
            "password": "password123",
            "role": "Restaurant Manager",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "jane.tan@restaurant.com"
    assert body["role"] == "Restaurant Manager"
    assert "password" not in body
    assert "password_hash" not in body


def test_register_rejects_duplicate_email(client):
    """FR1.6."""
    payload = {
        "name": "Jane Tan",
        "email": "dupe@restaurant.com",
        "password": "password123",
        "role": "Kitchen Staff",
    }
    first = client.post("/auth/register", json=payload)
    second = client.post("/auth/register", json=payload)
    assert first.status_code == 201
    assert second.status_code == 409


def test_login_returns_token_and_role(client):
    client.post(
        "/auth/register",
        json={
            "name": "Jane Tan",
            "email": "jane@restaurant.com",
            "password": "password123",
            "role": "Kitchen Staff",
        },
    )
    resp = client.post(
        "/auth/login", json={"email": "jane@restaurant.com", "password": "password123"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "Kitchen Staff"
    assert body["access_token"]


def test_login_wrong_password_is_generic_error(client):
    """FR1.7 — must not reveal whether the email or the password was wrong."""
    client.post(
        "/auth/register",
        json={
            "name": "Jane Tan",
            "email": "jane2@restaurant.com",
            "password": "password123",
            "role": "Kitchen Staff",
        },
    )
    wrong_password = client.post(
        "/auth/login", json={"email": "jane2@restaurant.com", "password": "wrongpass"}
    )
    nonexistent_email = client.post(
        "/auth/login", json={"email": "nobody@restaurant.com", "password": "wrongpass"}
    )
    assert wrong_password.status_code == 401
    assert nonexistent_email.status_code == 401
    assert wrong_password.json()["detail"] == nonexistent_email.json()["detail"]


def test_unauthenticated_request_is_rejected(client):
    resp = client.get("/users/me")
    assert resp.status_code == 401


def test_non_manager_cannot_list_users(client):
    """FR1.3 — RBAC enforced server-side."""
    token = register_and_login(client, email="kitchen@restaurant.com", role="Kitchen Staff")
    resp = client.get("/users", headers=auth_headers(token))
    assert resp.status_code == 403


def test_manager_can_deactivate_staff_account(client):
    """FR1.4."""
    manager_token = register_and_login(
        client, email="manager@restaurant.com", role="Restaurant Manager"
    )
    client.post(
        "/auth/register",
        json={
            "name": "Kitchen Guy",
            "email": "staff@restaurant.com",
            "password": "password123",
            "role": "Kitchen Staff",
        },
    )
    users = client.get("/users", headers=auth_headers(manager_token)).json()
    staff = next(u for u in users if u["email"] == "staff@restaurant.com")

    resp = client.patch(
        f"/users/{staff['user_id']}",
        json={"is_active": False},
        headers=auth_headers(manager_token),
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


def test_manager_can_view_audit_log(client):
    """FR1.5 — the audit log Sprint 1 started writing is now actually
    readable, not just write-only."""
    manager_token = register_and_login(client, email="manager2@restaurant.com", role="Restaurant Manager")
    # register + login themselves are logged (see app/services/auth.py).
    resp = client.get("/users/audit-logs", headers=auth_headers(manager_token))
    assert resp.status_code == 200
    actions = [entry["action"] for entry in resp.json()]
    assert "register" in actions
    assert "login" in actions


def test_audit_log_records_staff_updates(client):
    """FR1.4 + FR1.5 together — a staff update shows up in the log."""
    manager_token = register_and_login(client, email="manager3@restaurant.com", role="Restaurant Manager")
    client.post(
        "/auth/register",
        json={
            "name": "Kitchen Person",
            "email": "kitchenperson@restaurant.com",
            "password": "password123",
            "role": "Kitchen Staff",
        },
    )
    users = client.get("/users", headers=auth_headers(manager_token)).json()
    staff = next(u for u in users if u["email"] == "kitchenperson@restaurant.com")
    client.patch(
        f"/users/{staff['user_id']}",
        json={"is_active": False},
        headers=auth_headers(manager_token),
    )

    resp = client.get("/users/audit-logs", headers=auth_headers(manager_token))
    actions = [entry["action"] for entry in resp.json()]
    assert any(a.startswith(f"update_user:{staff['user_id']}:") for a in actions)


def test_non_manager_cannot_view_audit_log(client):
    """FR1.3 RBAC applied to the audit log endpoint."""
    token = register_and_login(client, email="kitchen6@restaurant.com", role="Kitchen Staff")
    resp = client.get("/users/audit-logs", headers=auth_headers(token))
    assert resp.status_code == 403
