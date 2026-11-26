"""US2: the online pool and a store pool move independently (I2, SC-001)."""

from decimal import Decimal

import pytest

from apps.identity.models import User
from apps.identity.permissions import STORE_DENIED
from apps.inventory.models import Pool, Stock, StockEvent

pytestmark = pytest.mark.django_db

MOVEMENTS = "/api/stock/movements/"
STOCK = "/api/stock/"


def body(product, pool, store=None, **overrides):
    payload = {
        "product": str(product.pk),
        "pool": pool,
        "store": str(store.pk) if store is not None else None,
        "type": "RECEIVED",
        "quantity": "1",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def three_pools(make_product, make_stock, make_store):
    product = make_product(name="Milk", unit="L")
    store_a = make_store(name="Downtown")
    store_b = make_store(name="Riverside")
    row_a = make_stock(product=product, store=store_a, current_stock=Decimal(10))
    row_b = make_stock(product=product, store=store_b, current_stock=Decimal(10))
    row_online = make_stock(
        product=product, pool_type=Pool.ONLINE, current_stock=Decimal(10)
    )
    return product, store_a, store_b, row_a, row_b, row_online


def test_one_operation_changes_one_pool(as_user, make_user, three_pools):
    product, store_a, store_b, row_a, row_b, row_online = three_pools
    admin = make_user(role=User.Role.ADMIN, stores=[store_a, store_b])

    as_user(admin).post(
        MOVEMENTS, body(product, Pool.ONLINE, quantity="3"), format="json"
    )

    for row in (row_a, row_b, row_online):
        row.refresh_from_db()
    assert row_online.current_stock == Decimal(13)
    assert row_a.current_stock == Decimal(10)
    assert row_b.current_stock == Decimal(10)
    assert StockEvent.objects.count() == 1


def test_a_branch_write_leaves_the_online_pool_alone(as_user, make_user, three_pools):
    product, store_a, _store_b, row_a, _row_b, row_online = three_pools
    manager = make_user(role=User.Role.MANAGER, stores=[store_a])

    as_user(manager).post(
        MOVEMENTS,
        body(product, Pool.BRANCH, store_a, type="WASTE", quantity="4", note="expired"),
        format="json",
    )

    row_a.refresh_from_db()
    row_online.refresh_from_db()
    assert row_a.current_stock == Decimal(6)
    assert row_online.current_stock == Decimal(10)


def test_both_pools_of_one_product_are_separate_rows(three_pools):
    product, _store_a, _store_b, row_a, _row_b, row_online = three_pools
    assert Stock.objects.filter(product=product).count() == 3
    assert row_a.pk != row_online.pk


@pytest.mark.parametrize(
    ("pool", "with_store"),
    [(Pool.BRANCH, False), (Pool.ONLINE, True)],
)
def test_pool_and_store_must_agree(
    as_user, make_user, make_product, make_store, pool, with_store
):
    store = make_store()
    product = make_product()
    admin = make_user(role=User.Role.ADMIN, stores=[store])

    response = as_user(admin).post(
        MOVEMENTS,
        body(product, pool, store if with_store else None),
        format="json",
    )

    assert response.status_code == 400
    assert "store" in response.json()
    assert Stock.objects.count() == 0


def test_manager_cannot_reach_the_online_pool(as_user, make_user, three_pools):
    _product, store_a, _store_b, _row_a, _row_b, _row_online = three_pools
    manager = make_user(role=User.Role.MANAGER, stores=[store_a])
    client = as_user(manager)

    listed = client.get(STOCK)
    refused = client.post(MOVEMENTS, body(_product, Pool.ONLINE), format="json")

    assert listed.status_code == 200
    pools = [row["pool"] for row in listed.json()["results"]]
    assert pools == [Pool.BRANCH]
    assert refused.status_code == 403
    assert refused.json()["detail"] == STORE_DENIED


def test_regional_manager_reaches_every_pool(as_user, make_user, three_pools):
    product, store_a, store_b, _row_a, _row_b, row_online = three_pools
    regional = make_user(role=User.Role.REGIONAL_MANAGER, stores=[store_a, store_b])
    client = as_user(regional)

    response = client.post(
        MOVEMENTS, body(product, Pool.ONLINE, quantity="2"), format="json"
    )
    listed = client.get(STOCK)

    assert response.status_code == 201, response.content
    assert len(listed.json()["results"]) == 3
    row_online.refresh_from_db()
    assert row_online.current_stock == Decimal(12)


def test_online_filter_is_refused_below_regional_manager(
    as_user, make_user, three_pools
):
    _product, store_a, _store_b, _row_a, _row_b, _row_online = three_pools
    manager = make_user(role=User.Role.MANAGER, stores=[store_a])

    response = as_user(manager).get(STOCK, {"pool": Pool.ONLINE})

    assert response.status_code == 403
    assert response.json()["detail"] == STORE_DENIED


def test_deleting_a_store_takes_its_stock_and_events(
    as_user, make_user, make_product, make_stock, make_store
):
    store = make_store()
    product = make_product()
    make_stock(product=product, store=store, current_stock=Decimal(5))
    admin = make_user(role=User.Role.ADMIN, stores=[store])

    from apps.inventory.models import StockEvent as Event

    Event.objects.create(
        stock=Stock.objects.get(),
        product_id=product.pk,
        pool_type=Pool.BRANCH,
        store_id=store.pk,
        kind="MOVEMENT",
        type="RECEIVED",
        quantity=Decimal(5),
        by_id=admin.pk,
        by_name="Admin",
        at="2026-11-26T08:00:00Z",
    )

    response = as_user(admin).delete(f"/api/stores/{store.pk}/")

    assert response.status_code == 204, response.content
    assert Stock.objects.count() == 0
    assert Event.objects.count() == 0
