"""User Story 3: every store owned endpoint honours the store filter."""

import pytest

from apps.catalog.models import Product
from apps.identity.models import User
from apps.stores.models import Store

STORES = "/api/stores/"
PRODUCTS = "/api/products/"

STORE_DENIED = "This record is outside your store access."
ROLE_DENIED = "Your role may not perform this action."


def store_url(store):
    return f"{STORES}{store.pk}/"


@pytest.fixture
def downtown(make_store):
    return make_store(name="Downtown")


@pytest.fixture
def uptown(make_store):
    return make_store(name="Uptown")


@pytest.fixture
def admin(make_user):
    return make_user(role=User.Role.ADMIN, email="admin@example.com")


@pytest.fixture
def manager(make_user, downtown):
    return make_user(
        role=User.Role.MANAGER, stores=[downtown], email="manager@example.com"
    )


@pytest.fixture
def regional(make_user, downtown, uptown):
    return make_user(
        role=User.Role.REGIONAL_MANAGER,
        stores=[downtown, uptown],
        email="regional@example.com",
    )


# Listing


def test_manager_sees_only_the_assigned_store(as_user, manager):
    response = as_user(manager).get(STORES)

    assert response.status_code == 200
    assert [row["name"] for row in response.data["results"]] == ["Downtown"]


def test_admin_sees_every_store(as_user, admin, downtown, uptown):
    response = as_user(admin).get(STORES)

    assert [row["name"] for row in response.data["results"]] == [
        "Downtown",
        "Uptown",
    ]


def test_regional_manager_sees_every_assigned_store(as_user, regional):
    response = as_user(regional).get(STORES)

    assert {row["name"] for row in response.data["results"]} == {
        "Downtown",
        "Uptown",
    }


def test_stores_are_ordered_by_name(as_user, admin, make_store):
    make_store(name="Beta")
    make_store(name="Alpha")

    response = as_user(admin).get(STORES)

    assert [row["name"] for row in response.data["results"]] == ["Alpha", "Beta"]


def test_stores_list_is_paginated(as_user, admin, make_store):
    for number in range(21):
        make_store(name=f"Store {number:02d}")

    response = as_user(admin).get(STORES)

    assert response.data["count"] == 21
    assert len(response.data["results"]) == 20


def test_empty_assignments_get_an_empty_list(as_user, make_user, downtown):
    barista = make_user(role=User.Role.BARISTA, email="barista@example.com")

    response = as_user(barista).get(STORES)

    assert response.status_code == 200
    assert response.data["count"] == 0
    assert response.data["results"] == []


# Detail reads


def test_manager_reads_an_own_store(as_user, manager, downtown):
    response = as_user(manager).get(store_url(downtown))

    assert response.status_code == 200
    assert response.data["name"] == "Downtown"


def test_manager_cannot_read_a_cross_store(as_user, manager, uptown):
    response = as_user(manager).get(store_url(uptown))

    assert response.status_code == 403
    assert response.data == {"detail": STORE_DENIED}


# Writes below manager


def test_barista_cannot_create_a_store(as_user, make_user):
    barista = make_user(role=User.Role.BARISTA, email="barista@example.com")

    response = as_user(barista).post(STORES, {"name": "New"}, format="json")

    assert response.status_code == 403
    assert response.data == {"detail": ROLE_DENIED}


def test_barista_cannot_rename_a_store(as_user, make_user, downtown):
    barista = make_user(role=User.Role.BARISTA, email="barista@example.com")

    response = as_user(barista).patch(
        store_url(downtown), {"name": "Renamed"}, format="json"
    )

    assert response.status_code == 403
    assert response.data == {"detail": ROLE_DENIED}


def test_manager_cannot_create_a_store(as_user, manager):
    response = as_user(manager).post(STORES, {"name": "New"}, format="json")

    assert response.status_code == 403
    assert response.data == {"detail": ROLE_DENIED}


def test_manager_cannot_rename_a_store(as_user, manager, downtown):
    response = as_user(manager).patch(
        store_url(downtown), {"name": "Renamed"}, format="json"
    )

    assert response.status_code == 403
    assert response.data == {"detail": ROLE_DENIED}


def test_manager_cannot_delete_a_store(as_user, manager, downtown):
    response = as_user(manager).delete(store_url(downtown))

    assert response.status_code == 403
    assert response.data == {"detail": ROLE_DENIED}
    assert Store.objects.filter(pk=downtown.pk).exists()


# Writes for regional manager and admin


def test_regional_manager_creates_a_store(as_user, regional):
    response = as_user(regional).post(
        STORES,
        {"name": "Riverside", "address": "3 River Road", "postal_code": "33333"},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["name"] == "Riverside"
    created = Store.objects.get(pk=response.data["id"])
    assert created.name == "Riverside"
    regional.refresh_from_db()
    assert created.pk in regional.store_ids
    listing = as_user(regional).get(STORES)
    assert "Riverside" in [row["name"] for row in listing.data["results"]]


def test_regional_manager_renames_a_store(as_user, regional, downtown):
    response = as_user(regional).patch(
        store_url(downtown), {"name": "Downtown Two"}, format="json"
    )

    assert response.status_code == 200
    assert response.data["name"] == "Downtown Two"
    downtown.refresh_from_db()
    assert downtown.name == "Downtown Two"


def test_regional_manager_cannot_delete_a_store(as_user, regional, downtown):
    response = as_user(regional).delete(store_url(downtown))

    assert response.status_code == 403
    assert response.data == {"detail": ROLE_DENIED}
    assert Store.objects.filter(pk=downtown.pk).exists()


def test_admin_deletes_a_store(as_user, admin, downtown):
    response = as_user(admin).delete(store_url(downtown))

    assert response.status_code == 204
    assert not Store.objects.filter(pk=downtown.pk).exists()


def test_store_name_is_required(as_user, admin):
    response = as_user(admin).post(STORES, {"address": "1 Main"}, format="json")

    assert response.status_code == 400
    assert "name" in response.data


def test_store_name_is_limited_to_40_characters(as_user, admin):
    response = as_user(admin).post(STORES, {"name": "x" * 41}, format="json")

    assert response.status_code == 400
    assert "name" in response.data


# Catalog stays global


@pytest.mark.parametrize("role", User.Role.values)
def test_catalog_is_global_for_every_role(as_user, make_user, role):
    Product.objects.create(name="Espresso", description="Short", price="2.50")
    actor = make_user(role=role, email="actor@example.com")

    response = as_user(actor).get(PRODUCTS)

    assert response.status_code == 200
    assert "Espresso" in [row["name"] for row in response.data["results"]]


def test_catalog_requires_a_session(api_client):
    assert api_client.get(PRODUCTS).status_code == 401


def test_stores_require_a_session(api_client):
    assert api_client.get(STORES).status_code == 401
