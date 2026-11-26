"""Store scope on stock: exactly zero leakage, and the message carries no field."""

from decimal import Decimal

import pytest

from apps.identity.models import User
from apps.identity.permissions import STORE_DENIED
from apps.inventory.models import Stock

pytestmark = pytest.mark.django_db

STOCK = "/api/stock/"


@pytest.fixture
def two_stores(make_store, make_product, make_stock):
    home = make_store(name="Downtown")
    other = make_store(name="Riverside")
    product = make_product(name="Milk")
    mine = make_stock(product=product, store=home, current_stock=Decimal(4))
    theirs = make_stock(product=product, store=other, current_stock=Decimal(9))
    return home, other, mine, theirs


def test_a_manager_sees_exactly_zero_foreign_rows(as_user, make_user, two_stores):
    home, _other, mine, theirs = two_stores
    manager = make_user(role=User.Role.MANAGER, stores=[home])

    response = as_user(manager).get(STOCK)

    ids = [row["id"] for row in response.json()["results"]]
    assert ids == [str(mine.pk)]
    assert str(theirs.pk) not in ids
    assert response.json()["count"] == 1


def test_a_foreign_history_request_is_refused_without_leaking(
    as_user, make_user, two_stores
):
    home, _other, _mine, theirs = two_stores
    manager = make_user(role=User.Role.MANAGER, stores=[home])

    response = as_user(manager).get(f"/api/stock/{theirs.pk}/events/")

    assert response.status_code == 403
    assert response.json() == {"detail": STORE_DENIED}


def test_a_store_filter_outside_the_assignments_is_forbidden(
    as_user, make_user, two_stores
):
    _home, other, _mine, _theirs = two_stores
    manager = make_user(role=User.Role.MANAGER, stores=[_home])

    response = as_user(manager).get(STOCK, {"store": str(other.pk)})

    assert response.status_code == 403
    assert response.json()["detail"] == STORE_DENIED


def test_no_assignments_means_an_empty_list(as_user, make_user, two_stores):
    user = make_user(role=User.Role.BARISTA, stores=[])

    response = as_user(user).get(STOCK)

    assert response.status_code == 200
    assert response.json()["count"] == 0
    assert response.json()["results"] == []


def test_an_admin_sees_every_store(as_user, make_user, two_stores):
    home, other, _mine, _theirs = two_stores
    admin = make_user(role=User.Role.ADMIN, stores=[home, other])

    response = as_user(admin).get(STOCK)

    assert response.json()["count"] == 2


def test_an_unauthenticated_request_is_refused(api_client, two_stores):
    response = api_client.get(STOCK)

    assert response.status_code == 401


def test_a_malformed_path_id_is_a_404(as_user, make_user, two_stores):
    home, _other, _mine, _theirs = two_stores
    manager = make_user(role=User.Role.MANAGER, stores=[home])

    response = as_user(manager).get("/api/stock/not-an-id/events/")

    assert response.status_code == 404
    assert Stock.objects.count() == 2
