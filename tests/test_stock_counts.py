"""US4: a count sets the number, resets the baseline, and the gap is derived."""

from decimal import Decimal

import pytest

from apps.identity.models import User
from apps.inventory.models import EventKind, Stock, StockEvent
from apps.inventory.services import derived_discrepancy

pytestmark = pytest.mark.django_db

MOVEMENTS = "/api/stock/movements/"
COUNTS = "/api/stock/counts/"


def record(client, product, store, **overrides):
    payload = {
        "product": str(product.pk),
        "pool": "BRANCH",
        "store": str(store.pk),
    }
    payload.update(overrides)
    return client.post(COUNTS, payload, format="json")


def move(client, product, store, **overrides):
    payload = {
        "product": str(product.pk),
        "pool": "BRANCH",
        "store": str(store.pk),
        "type": "RECEIVED",
        "quantity": "1",
    }
    payload.update(overrides)
    return client.post(MOVEMENTS, payload, format="json")


@pytest.fixture
def shelf(as_user, make_store, make_product, make_user):
    store = make_store(name="Downtown")
    product = make_product(name="Milk", unit="L")
    manager = make_user(role=User.Role.MANAGER, stores=[store])
    return as_user(manager), store, product


def test_a_count_sets_the_number(shelf, make_stock):
    client, store, product = shelf
    stock = make_stock(product=product, store=store, current_stock=Decimal(8))

    response = record(client, product, store, counted="6")

    assert response.status_code == 201, response.content
    assert response.json()["stock"]["current_stock"] == "6"
    assert response.json()["stock"]["last_count"] == "6"
    stock.refresh_from_db()
    assert stock.current_stock == Decimal(6)
    assert stock.last_count == Decimal(6)
    assert stock.last_count_at is not None


def test_a_count_above_the_number_raises_it(shelf, make_stock):
    client, store, product = shelf
    stock = make_stock(product=product, store=store, current_stock=Decimal(8))

    response = record(client, product, store, counted="11")

    assert response.status_code == 201, response.content
    stock.refresh_from_db()
    assert stock.current_stock == Decimal(11)


def test_a_count_equal_to_the_number_is_stored(shelf, make_stock):
    client, store, product = shelf
    stock = make_stock(product=product, store=store, current_stock=Decimal(8))

    response = record(client, product, store, counted="8")

    assert response.status_code == 201, response.content
    stock.refresh_from_db()
    assert stock.current_stock == Decimal(8)
    assert StockEvent.objects.filter(kind=EventKind.COUNT).count() == 1


def test_an_empty_shelf_is_a_real_observation(shelf, make_stock):
    client, store, product = shelf
    stock = make_stock(product=product, store=store, current_stock=Decimal(4))

    response = record(client, product, store, counted="0")

    assert response.status_code == 201, response.content
    stock.refresh_from_db()
    assert stock.current_stock == Decimal(0)


def test_a_negative_count_is_refused(shelf, make_stock):
    client, store, product = shelf
    stock = make_stock(product=product, store=store, current_stock=Decimal(4))

    response = record(client, product, store, counted="-1")

    assert response.status_code == 400
    stock.refresh_from_db()
    assert stock.current_stock == Decimal(4)


@pytest.mark.parametrize(("field", "value"), [("type", "RECEIVED"), ("quantity", "3")])
def test_a_count_carries_no_direction(shelf, make_stock, field, value):
    client, store, product = shelf
    make_stock(product=product, store=store, current_stock=Decimal(4))

    response = record(client, product, store, counted="4", **{field: value})

    assert response.status_code == 400
    assert field in response.json()


def test_a_delivery_applies_on_top_of_a_count(shelf, make_stock):
    client, store, product = shelf
    stock = make_stock(product=product, store=store, current_stock=Decimal(8))

    record(client, product, store, counted="6", at="2026-11-26T10:00:00Z")
    response = move(client, product, store, quantity="4", at="2026-11-26T11:00:00Z")

    assert response.status_code == 201, response.content
    stock.refresh_from_db()
    assert stock.current_stock == Decimal(10)


def test_a_movement_before_the_newest_count_is_refused(shelf, make_stock):
    client, store, product = shelf
    stock = make_stock(product=product, store=store, current_stock=Decimal(8))
    record(client, product, store, counted="6", at="2026-11-26T10:00:00Z")

    response = move(client, product, store, quantity="1", at="2026-11-26T09:30:00Z")

    assert response.status_code == 400
    assert "at" in response.json()
    stock.refresh_from_db()
    assert stock.current_stock == Decimal(6)


def test_a_movement_after_the_newest_count_is_accepted(shelf, make_stock):
    client, store, product = shelf
    stock = make_stock(product=product, store=store, current_stock=Decimal(8))
    record(client, product, store, counted="6", at="2026-11-26T10:00:00Z")

    response = move(client, product, store, quantity="1", at="2026-11-26T10:00:01Z")

    assert response.status_code == 201, response.content
    stock.refresh_from_db()
    assert stock.current_stock == Decimal(7)


def test_the_discrepancy_is_derived_from_events(shelf):
    client, store, product = shelf
    move(client, product, store, quantity="12.5", at="2026-11-26T08:00:00Z")
    move(
        client,
        product,
        store,
        type="WASTE",
        quantity="2",
        note="expired",
        at="2026-11-26T09:00:00Z",
    )
    record(client, product, store, counted="9", at="2026-11-26T10:00:00Z")

    stock = Stock.objects.get()

    assert stock.current_stock == Decimal(9)
    assert derived_discrepancy(stock) == Decimal("1.500")


def test_the_first_count_uses_a_zero_baseline(shelf):
    client, store, product = shelf
    move(client, product, store, quantity="5", at="2026-11-26T08:00:00Z")
    record(client, product, store, counted="4", at="2026-11-26T10:00:00Z")

    stock = Stock.objects.get()

    assert derived_discrepancy(stock) == Decimal("1.000")


def test_no_count_means_no_discrepancy(shelf):
    client, store, product = shelf
    move(client, product, store, quantity="5", at="2026-11-26T08:00:00Z")

    assert derived_discrepancy(Stock.objects.get()) is None


def test_a_second_count_measures_only_its_own_window(shelf):
    client, store, product = shelf
    move(client, product, store, quantity="10", at="2026-11-26T08:00:00Z")
    record(client, product, store, counted="9", at="2026-11-26T10:00:00Z")
    move(client, product, store, quantity="5", at="2026-11-26T11:00:00Z")
    record(client, product, store, counted="13", at="2026-11-26T12:00:00Z")

    stock = Stock.objects.get()

    assert stock.current_stock == Decimal(13)
    assert derived_discrepancy(stock) == Decimal("1.000")
