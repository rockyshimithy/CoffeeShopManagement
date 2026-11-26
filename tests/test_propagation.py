"""User Story 3: store assignments stay in sync with the store list."""

import threading

import pytest
from bson import ObjectId
from django.db import connections

from apps.identity import services as identity_services
from apps.identity.models import User
from apps.stores import services as store_services

STORES = "/api/stores/"
ACCOUNTS = "/api/accounts/"


@pytest.fixture
def admin(make_user):
    return make_user(role=User.Role.ADMIN, email="admin@example.com")


@pytest.fixture
def downtown(make_store):
    return make_store(name="Downtown")


@pytest.fixture
def uptown(make_store):
    return make_store(name="Uptown")


def test_creating_a_store_appends_it_to_every_regional_manager(
    as_user, admin, make_user, downtown
):
    first = make_user(role=User.Role.REGIONAL_MANAGER, stores=[downtown])
    second = make_user(role=User.Role.REGIONAL_MANAGER, stores=[])

    response = as_user(admin).post(STORES, {"name": "Riverside"}, format="json")

    assert response.status_code == 201
    new_id = ObjectId(response.data["id"])
    for regional in (first, second):
        regional.refresh_from_db()
        assert new_id in regional.store_ids


def test_creating_a_regional_manager_assigns_every_store(
    as_user, admin, downtown, uptown
):
    response = as_user(admin).post(
        ACCOUNTS,
        {
            "email": "new-regional@example.com",
            "password": "test-password-123",
            "role": User.Role.REGIONAL_MANAGER,
        },
        format="json",
    )

    assert response.status_code == 201
    assert set(response.data["store_ids"]) == {str(downtown.pk), str(uptown.pk)}


def test_deleting_a_store_removes_it_from_every_user(
    as_user, admin, make_user, downtown
):
    manager = make_user(role=User.Role.MANAGER, stores=[downtown])
    regional = make_user(role=User.Role.REGIONAL_MANAGER, stores=[downtown])

    response = as_user(admin).delete(f"{STORES}{downtown.pk}/")

    assert response.status_code == 204
    for user in (manager, regional):
        user.refresh_from_db()
        assert downtown.pk not in user.store_ids


def test_a_regional_manager_sees_the_next_store_created(as_user, admin):
    created = as_user(admin).post(
        ACCOUNTS,
        {
            "email": "early-regional@example.com",
            "password": "test-password-123",
            "role": User.Role.REGIONAL_MANAGER,
        },
        format="json",
    )
    assert created.data["store_ids"] == []

    as_user(admin).post(STORES, {"name": "First store"}, format="json")

    regional = User.objects.get(email="early-regional@example.com")
    listing = as_user(regional).get(STORES)
    assert [row["name"] for row in listing.data["results"]] == ["First store"]


@pytest.mark.django_db(transaction=True)
def test_concurrent_store_creations_keep_both_assignments(monkeypatch):
    regional = User.objects.create_user(
        email="regional@example.com",
        password="test-password-123",
        role=User.Role.REGIONAL_MANAGER,
    )
    actor = User.objects.create_user(
        email="admin@example.com",
        password="test-password-123",
        role=User.Role.ADMIN,
    )

    barrier = threading.Barrier(2, timeout=15)
    local = threading.local()
    original = identity_services._update_store_ids
    calls = []

    def synced_update(user_id, store_ids):
        # Both threads read the same list before either writes, which is the
        # race the write conflict probe reproduced.
        calls.append(store_ids)
        if not getattr(local, "synced", False):
            local.synced = True
            barrier.wait()
        original(user_id, store_ids)

    monkeypatch.setattr(identity_services, "_update_store_ids", synced_update)
    errors = []

    def worker(name):
        try:
            store_services.create_store(actor, {"name": name})
        except Exception as exc:  # noqa: BLE001 - the test reports what it got
            errors.append(exc)
        finally:
            connections["default"].close()

    threads = [
        threading.Thread(target=worker, args=(f"Concurrent {number}",))
        for number in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    # Two first attempts plus one replay after the conflict the barrier forced.
    assert len(calls) == 3
    regional.refresh_from_db()
    assert len(regional.store_ids) == 2
