"""Shared fixtures for the M0 test suites.

The factory fixtures below request ``db`` in their own signatures, so a test gets
database access by naming the factory it uses. Nothing here opens a network
connection: the tests talk to the same MongoDB the app uses.
"""

import itertools
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from bson import ObjectId
from rest_framework.test import APIClient

from apps.catalog.models import Product
from apps.identity.models import Employee, User
from apps.inventory.models import EventKind, Movement, Pool, Stock, StockEvent
from apps.stores.models import Store
from apps.workforce.models import Shift

PASSWORD = "test-password-123"

SHIFT_START = datetime(2026, 11, 30, 8, 0, tzinfo=UTC)
SHIFT_END = datetime(2026, 11, 30, 16, 0, tzinfo=UTC)

EVENT_START = datetime(2026, 11, 24, 8, 0, tzinfo=UTC)

_emails = itertools.count(1)
_names = itertools.count(1)


@pytest.fixture
def make_store(db):
    def _make(name=None, address="12 Main Street", postal_code="12345"):
        return Store.objects.create(
            name=name or f"Store {next(_names)}",
            address=address,
            postal_code=postal_code,
        )

    return _make


@pytest.fixture
def make_user(db):
    def _make(
        role=User.Role.BARISTA, stores=(), email=None, password=PASSWORD, **extra
    ):
        return User.objects.create_user(
            email=email or f"user{next(_emails)}@example.com",
            password=password,
            role=role,
            store_ids=[store.pk for store in stores],
            **extra,
        )

    return _make


@pytest.fixture
def make_employee(db, make_user):
    def _make(user=None, hire_date="2026-11-01", **user_extra):
        return Employee.objects.create(
            user=user or make_user(**user_extra), hire_date=hire_date
        )

    return _make


@pytest.fixture
def make_shift(db, make_employee, make_store):
    def _make(employee=None, store=None, starts_at=SHIFT_START, ends_at=SHIFT_END):
        return Shift.objects.create(
            employee=employee or make_employee(),
            store=store or make_store(),
            starts_at=starts_at,
            ends_at=ends_at,
        )

    return _make


@pytest.fixture
def make_product(db):
    def _make(
        name=None, unit="pcs", price=None, threshold=None, description="", **extra
    ):
        return Product.objects.create(
            name=name or f"Product {next(_names)}",
            description=description,
            unit=unit,
            price=price,
            low_stock_threshold=threshold,
            **extra,
        )

    return _make


@pytest.fixture
def make_stock(db, make_product, make_store):
    def _make(
        product=None, pool_type=Pool.BRANCH, store=None, current_stock=0, **extra
    ):
        if pool_type == Pool.BRANCH and store is None:
            store = make_store()
        return Stock.objects.create(
            product=product or make_product(),
            pool_type=pool_type,
            store=store,
            current_stock=current_stock,
            **extra,
        )

    return _make


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def as_user(api_client):
    """Sign a client in through a real session, without the login endpoint."""

    def _login(user):
        api_client.force_login(user)
        return api_client

    return _login


def _event_values(stock, at, fields):
    """Defaults for one event. The write path is bypassed, so no validator runs."""
    values = {
        "stock": stock,
        "product_id": stock.product_id,
        "pool_type": stock.pool_type,
        "store_id": stock.store_id,
        "kind": EventKind.MOVEMENT,
        "type": Movement.RECEIVED,
        "quantity": Decimal(1),
        "by_id": ObjectId(),
        "by_name": "Test Actor",
        "at": at,
    }
    values.update(fields)
    if values["type"] == Movement.WASTE and not values.get("note"):
        values["note"] = "Spilled"
    return values


@pytest.fixture
def make_event(db):
    def _make(stock, **fields):
        return StockEvent.objects.create(**_event_values(stock, EVENT_START, fields))

    return _make


@pytest.fixture
def make_events(db):
    def _make(count, *, stock, at=EVENT_START, step=timedelta(seconds=1), **fields):
        rows = [
            StockEvent(**_event_values(stock, at + step * i, fields))
            for i in range(count)
        ]
        StockEvent.objects.bulk_create(rows, batch_size=1000)
        return rows

    return _make
