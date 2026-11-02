"""Two rules tightened before the system preview.

1. Accounts: in production nobody can register themselves once the first
   Manager/Owner exists; a Manager or an Owner creates every other account.
2. Suppliers: a deactivated supplier can be reactivated, cannot be ordered
   from, and a purchase order is priced from the supplier it is addressed to.
"""
from decimal import Decimal
from types import SimpleNamespace

from tests.conftest import auth_headers, register_and_login

NEW_STAFF = {"name": "New Staff", "email": "newstaff@restaurant.com", "password": "password123", "role": "Kitchen Staff"}


def _closed(monkeypatch, *, environment="production", enabled=None):
    monkeypatch.setattr(
        "app.services.auth.get_settings",
        lambda: SimpleNamespace(environment=environment, public_registration_enabled=enabled),
    )


def _register(client, **overrides):
    return client.post("/auth/register", json={**NEW_STAFF, **overrides})


class TestAccountCreation:
    def test_open_in_development_so_tests_and_seeding_keep_working(self, client):
        assert _register(client).status_code == 201

    def test_in_production_the_first_account_must_be_a_manager_or_owner(self, client, monkeypatch):
        _closed(monkeypatch)

        refused = _register(client)  # a Kitchen account, with nobody else yet
        assert refused.status_code == 403
        assert "Manager or Owner" in refused.json()["detail"]

        assert _register(client, email="boss@restaurant.com", role="Restaurant Manager").status_code == 201

    def test_in_production_nobody_can_register_themselves_after_that(self, client, monkeypatch):
        _closed(monkeypatch)
        _register(client, email="boss@restaurant.com", role="Restaurant Manager")

        for role in ("Kitchen Staff", "Inventory Staff", "Procurement Officer", "Delivery/Logistics Staff"):
            assert _register(client, email=f"{role[:4]}@restaurant.com".replace("/", ""), role=role).status_code == 403

    def test_the_setting_can_close_registration_outside_production(self, client, monkeypatch):
        _closed(monkeypatch, environment="development", enabled=False)
        assert _register(client).status_code == 403

    def test_the_setting_can_open_registration_in_production(self, client, monkeypatch):
        _closed(monkeypatch, enabled=True)
        assert _register(client).status_code == 201

    def test_a_manager_creates_staff_accounts_and_they_can_log_in(self, client, monkeypatch):
        _closed(monkeypatch)
        _register(client, email="boss@restaurant.com", role="Restaurant Manager")
        manager = auth_headers(client.post("/auth/login", json={"email": "boss@restaurant.com", "password": "password123"}).json()["access_token"])

        assert client.post("/users", json=NEW_STAFF, headers=manager).status_code == 201
        login = client.post("/auth/login", json={"email": NEW_STAFF["email"], "password": NEW_STAFF["password"]})
        assert login.status_code == 200 and login.json()["role"] == "Kitchen Staff"

    def test_an_owner_can_create_and_list_accounts_too(self, client):
        owner = auth_headers(register_and_login(client, email="owner@restaurant.com", role="Restaurant Owner"))

        assert client.post("/users", json=NEW_STAFF, headers=owner).status_code == 201
        emails = [u["email"] for u in client.get("/users", headers=owner).json()]
        assert NEW_STAFF["email"] in emails
        assert client.get("/users/audit-logs", headers=owner).status_code == 200

    def test_other_roles_cannot_create_accounts(self, client):
        register_and_login(client, email="boss@restaurant.com", role="Restaurant Manager")
        for role in ("Kitchen Staff", "Inventory Staff", "Shift Supervisor", "Procurement Officer", "Delivery/Logistics Staff"):
            headers = auth_headers(register_and_login(client, email=f"{role[:5]}@restaurant.com".replace("/", ""), role=role))
            assert client.post("/users", json={**NEW_STAFF, "email": f"x{role[:5]}@restaurant.com".replace("/", "")}, headers=headers).status_code == 403
            assert client.get("/users", headers=headers).status_code == 403


def _supplier_setup(client):
    manager = auth_headers(register_and_login(client, email="manager@restaurant.com", role="Restaurant Manager"))
    officer = auth_headers(register_and_login(client, email="po@restaurant.com", role="Procurement Officer"))
    inventory = auth_headers(register_and_login(client, email="inv@restaurant.com", role="Inventory Staff"))
    rice = client.post(
        "/inventory/ingredients", json={"name": "Rice", "unit": "kg", "current_stock": "10"}, headers=inventory
    ).json()
    cheap = client.post("/procurement/suppliers", json={"name": "Cheap Co", "contact_info": "1"}, headers=officer).json()
    dear = client.post("/procurement/suppliers", json={"name": "Dear Co", "contact_info": "2"}, headers=officer).json()
    for supplier, price in ((cheap, "2.00"), (dear, "3.50")):
        client.post(
            "/procurement/suppliers/pricing",
            json={"supplier_id": supplier["supplier_id"], "ingredient_id": rice["ingredient_id"], "unit_price": price},
            headers=officer,
        ).raise_for_status()
    return manager, officer, rice, cheap, dear


def _order(client, officer, supplier, rice, qty="10"):
    return client.post(
        "/procurement/purchase-orders",
        json={"supplier_id": supplier["supplier_id"], "line_items": [{"ingredient_id": rice["ingredient_id"], "quantity": qty}]},
        headers=officer,
    )


class TestSuppliers:
    def test_a_purchase_order_is_priced_from_the_supplier_it_is_addressed_to(self, client):
        _manager, officer, rice, cheap, dear = _supplier_setup(client)

        assert Decimal(_order(client, officer, cheap, rice).json()["total_cost"]) == Decimal("20.00")
        assert Decimal(_order(client, officer, dear, rice).json()["total_cost"]) == Decimal("35.00")  # not 20.00

    def test_a_supplier_that_has_not_priced_the_item_falls_back_to_the_cheapest_active_price(self, client):
        _manager, officer, rice, cheap, _dear = _supplier_setup(client)
        unpriced = client.post("/procurement/suppliers", json={"name": "New Co", "contact_info": "3"}, headers=officer).json()

        assert Decimal(_order(client, officer, unpriced, rice).json()["total_cost"]) == Decimal("20.00")

    def test_a_deactivated_supplier_cannot_be_ordered_from_until_reactivated(self, client):
        _manager, officer, rice, cheap, _dear = _supplier_setup(client)
        sid = cheap["supplier_id"]

        assert client.patch(f"/procurement/suppliers/{sid}/deactivate", headers=officer).json()["is_active"] is False
        blocked = _order(client, officer, cheap, rice)
        assert blocked.status_code == 409 and "deactivated" in blocked.json()["detail"]

        reactivated = client.patch(f"/procurement/suppliers/{sid}/reactivate", headers=officer)
        assert reactivated.status_code == 200 and reactivated.json()["is_active"] is True
        assert _order(client, officer, cheap, rice).status_code == 201

    def test_reactivating_an_unknown_supplier_is_404(self, client):
        _manager, officer, *_ = _supplier_setup(client)
        assert client.patch("/procurement/suppliers/999/reactivate", headers=officer).status_code == 404

    def test_deactivating_the_only_pricing_supplier_zeroes_the_ingredient_cost_until_reactivated(self, client):
        """The knock-on effect the Suppliers screen now warns about."""
        _manager, officer, rice, cheap, dear = _supplier_setup(client)
        for supplier in (cheap, dear):
            client.patch(f"/procurement/suppliers/{supplier['supplier_id']}/deactivate", headers=officer)

        from app.services.procurement import get_unit_price
        from app.db.session import get_db  # noqa: F401  (session comes from the client override)

        # Read the price the way menu margins and waste costs do.
        db = next(client.app.dependency_overrides[get_db]())
        assert get_unit_price(db, rice["ingredient_id"]) == Decimal("0.00")

        client.patch(f"/procurement/suppliers/{cheap['supplier_id']}/reactivate", headers=officer)
        assert get_unit_price(db, rice["ingredient_id"]) == Decimal("2.00")
