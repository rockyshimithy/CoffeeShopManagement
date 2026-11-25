"""Shared fixtures for the M0 test suites.

Every test gets the database, so a module never has to repeat
``pytest.mark.django_db``. Nothing here opens a network connection: the tests
talk to the same MongoDB the app uses.
"""

import itertools

import pytest
from rest_framework.test import APIClient

from apps.identity.models import Employee, User
from apps.stores.models import Store

PASSWORD = "test-password-123"

_emails = itertools.count(1)
_names = itertools.count(1)


@pytest.fixture(autouse=True)
def _database(db):
    """Baseline database access for every test in this project."""


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
def api_client():
    return APIClient()


@pytest.fixture
def as_user(api_client):
    """Sign a client in through a real session, without the login endpoint."""

    def _login(user):
        api_client.force_login(user)
        return api_client

    return _login
