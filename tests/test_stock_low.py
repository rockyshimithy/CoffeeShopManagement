"""US5: strictly below, never guessed, worst first, and one role may set the level."""

from decimal import Decimal

import pytest

from apps.identity.models import User
from apps.identity.permissions import ROLE_DENIED
from apps.inventory.models import Pool

pytestmark = pytest.mark.django_db

LOW = "/api/stock/low/"
STOCK = "/api/stock/"


@pytest.fixture
def admin(as_user, make_store, make_user):
    store = make_store(name="Downtown")
    return as_user(make_user(role=User.Role.ADMIN, stores=[store])), store


def test_below_the_level_appears(admin, make_product, make_stock):
    client, store = admin
    product = make_product(threshold=Decimal(5))
    make_stock(product=product, store=store, current_stock=Decimal(3))

    response = client.get(LOW)

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["results"][0]["product_name"] == product.name
    assert body["results"][0]["current_stock"] == "3"
    assert body["results"][0]["is_low"] is True


def test_exactly_at_the_level_does_not_appear(admin, make_product, make_stock):
    client, store = admin
    product = make_product(threshold=Decimal(5))
    make_stock(product=product, store=store, current_stock=Decimal(5))

    response = client.get(LOW)

    assert response.json()["count"] == 0
    assert client.get(STOCK).json()["results"][0]["is_low"] is False


def test_no_level_is_never_low(admin, make_product, make_stock):
    client, store = admin
    product = make_product(threshold=None)
    make_stock(product=product, store=store, current_stock=Decimal(0))

    response = client.get(LOW)

    assert response.json()["count"] == 0
    assert client.get(STOCK).json()["results"][0]["is_low"] is False


def test_worst_first(admin, make_product, make_stock):
    client, store = admin
    worst = make_product(name="A milk", threshold=Decimal(10))
    middle = make_product(name="B milk", threshold=Decimal(5))
    least = make_product(name="C milk", threshold=Decimal(5))
    make_stock(product=worst, store=store, current_stock=Decimal(2))
    make_stock(product=middle, store=store, current_stock=Decimal(1))
    make_stock(product=least, store=store, current_stock=Decimal(4))

    response = client.get(LOW)

    names = [row["product_name"] for row in response.json()["results"]]
    assert names == ["A milk", "B milk", "C milk"]


def test_the_level_applies_in_every_pool(admin, make_product, make_stock):
    client, store = admin
    product = make_product(threshold=Decimal(5))
    make_stock(product=product, store=store, current_stock=Decimal(1))
    make_stock(product=product, pool_type=Pool.ONLINE, current_stock=Decimal(2))

    response = client.get(LOW)

    pools = sorted(row["pool"] for row in response.json()["results"])
    assert response.json()["count"] == 2
    assert pools == [Pool.BRANCH, Pool.ONLINE]


def test_a_barista_can_read_the_list(
    as_user, make_store, make_product, make_stock, make_user
):
    store = make_store()
    product = make_product(threshold=Decimal(5))
    make_stock(product=product, store=store, current_stock=Decimal(1))
    barista = make_user(role=User.Role.BARISTA, stores=[store])

    response = as_user(barista).get(LOW)

    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_a_manager_sees_only_their_own_stores(
    as_user, make_store, make_product, make_stock, make_user
):
    home = make_store()
    other = make_store()
    mine = make_product(name="Mine", threshold=Decimal(5))
    theirs = make_product(name="Theirs", threshold=Decimal(5))
    make_stock(product=mine, store=home, current_stock=Decimal(1))
    make_stock(product=theirs, store=other, current_stock=Decimal(1))
    manager = make_user(role=User.Role.MANAGER, stores=[home])

    response = as_user(manager).get(LOW)

    names = [row["product_name"] for row in response.json()["results"]]
    assert names == ["Mine"]


def test_only_admin_and_regional_manager_may_set_the_level(
    as_user, make_store, make_product, make_user
):
    store = make_store()
    product = make_product(threshold=None)
    manager = make_user(role=User.Role.MANAGER, stores=[store])
    regional = make_user(role=User.Role.REGIONAL_MANAGER, stores=[store])

    refused = as_user(manager).patch(
        f"/api/products/{product.pk}/", {"low_stock_threshold": "5"}, format="json"
    )
    allowed = as_user(regional).patch(
        f"/api/products/{product.pk}/", {"low_stock_threshold": "5"}, format="json"
    )

    assert refused.status_code == 403
    assert refused.json()["detail"] == ROLE_DENIED
    assert allowed.status_code == 200, allowed.content
    assert allowed.json()["low_stock_threshold"] == "5"


def test_clearing_the_level_stops_the_warning(admin, make_product, make_stock):
    client, store = admin
    product = make_product(threshold=Decimal(5))
    make_stock(product=product, store=store, current_stock=Decimal(1))
    assert client.get(LOW).json()["count"] == 1

    cleared = client.patch(
        f"/api/products/{product.pk}/", {"low_stock_threshold": None}, format="json"
    )

    assert cleared.status_code == 200, cleared.content
    assert cleared.json()["low_stock_threshold"] is None
    assert client.get(LOW).json()["count"] == 0
