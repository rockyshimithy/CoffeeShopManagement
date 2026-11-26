"""US1: a manager records a delivery, and the number and the history agree."""

from decimal import Decimal

import pytest
from django.db import DatabaseError

from apps.identity.models import User
from apps.identity.permissions import ROLE_DENIED
from apps.inventory.models import EventKind, Stock, StockEvent
from apps.inventory.services import CONFLICT, STOCK_ATTEMPTS

pytestmark = pytest.mark.django_db

MOVEMENTS = "/api/stock/movements/"
STOCK = "/api/stock/"


def movement_body(product, store, **overrides):
    payload = {
        "product": str(product.pk),
        "pool": "BRANCH" if store is not None else "ONLINE",
        "store": str(store.pk) if store is not None else None,
        "type": "RECEIVED",
        "quantity": "1",
    }
    payload.update(overrides)
    return payload


def test_delivery_raises_an_existing_number(
    as_user, make_store, make_product, make_stock, make_user
):
    store = make_store()
    product = make_product(unit="L")
    stock = make_stock(product=product, store=store, current_stock=Decimal(10))
    manager = make_user(role=User.Role.MANAGER, stores=[store])

    response = as_user(manager).post(
        MOVEMENTS, movement_body(product, store, quantity="12.5"), format="json"
    )

    assert response.status_code == 201, response.content
    assert response.json()["stock"]["current_stock"] == "22.5"
    stock.refresh_from_db()
    assert stock.current_stock == Decimal("22.500")


def test_first_delivery_creates_the_row(as_user, make_store, make_product, make_user):
    store = make_store()
    product = make_product()
    manager = make_user(role=User.Role.MANAGER, stores=[store])

    response = as_user(manager).post(
        MOVEMENTS, movement_body(product, store, quantity="12"), format="json"
    )

    assert response.status_code == 201, response.content
    assert Stock.objects.count() == 1
    assert response.json()["stock"]["current_stock"] == "12"


@pytest.mark.parametrize("quantity", ["0", "-1", "2.7515"])
def test_bad_quantity_is_refused(
    as_user, make_store, make_product, make_stock, make_user, quantity
):
    store = make_store()
    product = make_product()
    stock = make_stock(product=product, store=store, current_stock=Decimal(10))
    manager = make_user(role=User.Role.MANAGER, stores=[store])

    response = as_user(manager).post(
        MOVEMENTS, movement_body(product, store, quantity=quantity), format="json"
    )

    assert response.status_code == 400
    assert "quantity" in response.json()
    stock.refresh_from_db()
    assert stock.current_stock == Decimal(10)
    assert StockEvent.objects.count() == 0


def test_quantity_is_exact_on_a_repeated_read(
    as_user, make_store, make_product, make_user
):
    store = make_store()
    product = make_product(unit="L")
    manager = make_user(role=User.Role.MANAGER, stores=[store])
    client = as_user(manager)

    first = client.post(
        MOVEMENTS, movement_body(product, store, quantity="2.75"), format="json"
    )
    second = client.get(STOCK)

    assert first.json()["stock"]["current_stock"] == "2.75"
    assert second.json()["results"][0]["current_stock"] == "2.75"


def test_manager_cannot_record_into_another_store(
    as_user, make_store, make_product, make_user
):
    home = make_store()
    other = make_store()
    product = make_product()
    manager = make_user(role=User.Role.MANAGER, stores=[home])

    response = as_user(manager).post(
        MOVEMENTS, movement_body(product, other), format="json"
    )

    assert response.status_code == 403
    assert Stock.objects.count() == 0


def test_barista_cannot_record_but_can_read(
    as_user, make_store, make_product, make_stock, make_user
):
    store = make_store()
    product = make_product()
    stock = make_stock(product=product, store=store, current_stock=Decimal(7))
    barista = make_user(role=User.Role.BARISTA, stores=[store])
    client = as_user(barista)

    refused = client.post(MOVEMENTS, movement_body(product, store), format="json")
    read = client.get(STOCK)

    assert refused.status_code == 403
    assert refused.json()["detail"] == ROLE_DENIED
    assert read.status_code == 200
    assert read.json()["results"][0]["current_stock"] == "7"
    stock.refresh_from_db()
    assert stock.current_stock == Decimal(7)


def test_response_carries_the_row_and_the_event(
    as_user, make_store, make_product, make_user
):
    store = make_store(name="Downtown")
    product = make_product(name="Milk", unit="L")
    manager = make_user(
        role=User.Role.MANAGER, stores=[store], first_name="Ana", last_name="Silva"
    )

    response = as_user(manager).post(
        MOVEMENTS, movement_body(product, store, quantity="3"), format="json"
    )

    payload = response.json()
    assert payload["stock"]["product_name"] == "Milk"
    assert payload["stock"]["unit"] == "L"
    assert payload["stock"]["store_name"] == "Downtown"
    assert payload["event"]["by_name"] == "Ana Silva"
    assert payload["event"]["kind"] == EventKind.MOVEMENT
    assert payload["event"]["type"] == "RECEIVED"
    assert payload["event"]["quantity"] == "3"
    assert payload["event"]["note"] == ""


def test_every_event_names_actor_instant_and_kind(
    as_user, make_store, make_product, make_user
):
    store = make_store()
    product = make_product()
    manager = make_user(role=User.Role.MANAGER, stores=[store])

    as_user(manager).post(
        MOVEMENTS, movement_body(product, store, quantity="4"), format="json"
    )

    event = StockEvent.objects.get()
    assert event.by_id == manager.pk
    assert event.by_name
    assert event.at is not None
    assert event.kind == EventKind.MOVEMENT


def test_unknown_product_is_refused(as_user, make_store, make_user):
    store = make_store()
    manager = make_user(role=User.Role.MANAGER, stores=[store])

    response = as_user(manager).post(
        MOVEMENTS,
        {
            "product": "65f1c0a2b3d4e5f6a7b8c9d2",
            "pool": "BRANCH",
            "store": str(store.pk),
            "type": "RECEIVED",
            "quantity": "1",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "product" in response.json()
    assert Stock.objects.count() == 0


def test_malformed_product_id_is_refused(as_user, make_store, make_user):
    store = make_store()
    manager = make_user(role=User.Role.MANAGER, stores=[store])

    response = as_user(manager).post(
        MOVEMENTS, movement_body_for_raw_product(store), format="json"
    )

    assert response.status_code == 400
    assert "product" in response.json()


def movement_body_for_raw_product(store):
    return {
        "product": "not-an-object-id",
        "pool": "BRANCH",
        "store": str(store.pk),
        "type": "RECEIVED",
        "quantity": "1",
    }


def test_history_is_newest_first(as_user, make_store, make_product, make_user):
    store = make_store()
    product = make_product()
    manager = make_user(role=User.Role.MANAGER, stores=[store])
    client = as_user(manager)

    for quantity, at in (
        ("2", "2026-11-26T08:00:00Z"),
        ("3", "2026-11-26T09:00:00Z"),
    ):
        client.post(
            MOVEMENTS,
            movement_body(product, store, quantity=quantity, at=at),
            format="json",
        )

    stock = Stock.objects.get()
    response = client.get(f"/api/stock/{stock.pk}/events/")

    assert response.status_code == 200
    quantities = [row["quantity"] for row in response.json()["results"]]
    assert quantities == ["3", "2"]


def test_waste_subtracts_and_keeps_the_note(
    as_user, make_store, make_product, make_stock, make_user
):
    store = make_store()
    product = make_product()
    stock = make_stock(product=product, store=store, current_stock=Decimal(10))
    manager = make_user(
        role=User.Role.MANAGER, stores=[store], first_name="Ana", last_name="Silva"
    )

    response = as_user(manager).post(
        MOVEMENTS,
        movement_body(
            product, store, type="WASTE", quantity="2", note="expired on Tuesday"
        ),
        format="json",
    )

    assert response.status_code == 201, response.content
    assert response.json()["stock"]["current_stock"] == "8"
    stock.refresh_from_db()
    assert stock.current_stock == Decimal(8)
    event = StockEvent.objects.get()
    assert event.type == "WASTE"
    assert event.note == "expired on Tuesday"
    assert event.by_name == "Ana Silva"


def test_waste_larger_than_the_shelf_is_refused(
    as_user, make_store, make_product, make_stock, make_user
):
    store = make_store()
    product = make_product()
    stock = make_stock(product=product, store=store, current_stock=Decimal(10))
    manager = make_user(role=User.Role.MANAGER, stores=[store])

    response = as_user(manager).post(
        MOVEMENTS,
        movement_body(product, store, type="WASTE", quantity="11", note="typo"),
        format="json",
    )

    assert response.status_code == 400
    assert "quantity" in response.json()
    stock.refresh_from_db()
    assert stock.current_stock == Decimal(10)
    assert StockEvent.objects.count() == 0


def test_waste_to_zero_is_allowed(
    as_user, make_store, make_product, make_stock, make_user
):
    store = make_store()
    product = make_product()
    stock = make_stock(product=product, store=store, current_stock=Decimal(3))
    manager = make_user(role=User.Role.MANAGER, stores=[store])

    response = as_user(manager).post(
        MOVEMENTS,
        movement_body(product, store, type="WASTE", quantity="3", note="spilled"),
        format="json",
    )

    assert response.status_code == 201, response.content
    stock.refresh_from_db()
    assert stock.current_stock == Decimal(0)


@pytest.mark.parametrize("note", ["", "   "])
def test_waste_needs_a_note(
    as_user, make_store, make_product, make_stock, make_user, note
):
    store = make_store()
    product = make_product()
    stock = make_stock(product=product, store=store, current_stock=Decimal(10))
    manager = make_user(role=User.Role.MANAGER, stores=[store])

    response = as_user(manager).post(
        MOVEMENTS,
        movement_body(product, store, type="WASTE", quantity="1", note=note),
        format="json",
    )

    assert response.status_code == 400
    assert "note" in response.json()
    stock.refresh_from_db()
    assert stock.current_stock == Decimal(10)
    assert StockEvent.objects.count() == 0


def test_a_sale_in_a_branch_pool_is_refused(
    as_user, make_store, make_product, make_stock, make_user
):
    store = make_store()
    product = make_product()
    stock = make_stock(product=product, store=store, current_stock=Decimal(10))
    manager = make_user(role=User.Role.MANAGER, stores=[store])

    response = as_user(manager).post(
        MOVEMENTS,
        movement_body(product, store, type="SOLD", quantity="1"),
        format="json",
    )

    assert response.status_code == 400
    assert "type" in response.json()
    stock.refresh_from_db()
    assert stock.current_stock == Decimal(10)
    assert StockEvent.objects.count() == 0


def test_exhausted_retries_leave_a_resendable_conflict(
    as_user, make_store, make_product, make_stock, make_user, monkeypatch
):
    """FR-028: three lost rounds answer a conflict that says when to resend.

    The fault is injected at ``atomic``, so the real retry loop burns all three
    attempts and the real translation into ``StockConflict`` runs; only the
    database refusal is simulated.
    """
    store = make_store()
    product = make_product()
    stock = make_stock(product=product, store=store, current_stock=Decimal(10))
    manager = make_user(role=User.Role.MANAGER, stores=[store])
    attempts = []

    class Conflict:
        """Every transaction attempt is refused, the way two writers collide."""

        def __enter__(self):
            attempts.append(1)
            raise DatabaseError("write conflict")

        def __exit__(self, *exc):  # never reached: the enter above always raises
            return False

    monkeypatch.setattr("apps.inventory.services.atomic", Conflict)

    response = as_user(manager).post(
        MOVEMENTS, movement_body(product, store, quantity="1"), format="json"
    )

    assert len(attempts) == STOCK_ATTEMPTS, (
        "the retry cap is what the contract promises"
    )
    assert response.status_code == 409
    assert response["Retry-After"] == "1"
    assert response.json()["detail"] == CONFLICT
    stock = Stock.objects.get()
    assert stock.current_stock == Decimal(10)
    assert StockEvent.objects.count() == 0
