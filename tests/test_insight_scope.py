"""Cross-cutting scope, authorization, and the structural guard for both reads."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from apps.identity.models import User
from apps.identity.permissions import ROLE_ACTIONS, ROLE_DENIED, STORE_DENIED
from apps.inventory.models import Movement, Pool, Stock, StockEvent
from apps.stores.models import Store

pytestmark = pytest.mark.django_db

REPORT = "/api/stock/waste/"
FEED = "/api/stock/activity/"
START = datetime(2026, 11, 24, 8, 0, tzinfo=UTC)
END = datetime(2026, 11, 24, 23, 59, 59, 999000, tzinfo=UTC)
WINDOW = {
    "start": START.isoformat().replace("+00:00", "Z"),
    "end": END.isoformat().replace("+00:00", "Z"),
}


@pytest.fixture
def downtown(make_store):
    return make_store(name="Downtown")


@pytest.fixture
def uptown(make_store):
    return make_store(name="Uptown")


@pytest.fixture
def manager(make_user, downtown):
    return make_user(role=User.Role.MANAGER, stores=[downtown])


@pytest.fixture
def regional(make_user, downtown, uptown):
    return make_user(role=User.Role.REGIONAL_MANAGER, stores=[downtown, uptown])


@pytest.fixture
def admin(make_user):
    return make_user(role=User.Role.ADMIN)


def seed(make_stock, make_event, store=None, quantity="1", at=START):
    """One waste event, which both reads return. ``store=None`` is the online pool."""
    pool = Pool.ONLINE if store is None else Pool.BRANCH
    stock = make_stock(pool_type=pool, store=store)
    event = make_event(stock, type=Movement.WASTE, quantity=Decimal(quantity), at=at)
    return stock, event


def ids(body) -> list[str]:
    return [row["id"] for row in body["results"]]


def test_manager_in_store_a_sees_nothing_from_store_b(
    as_user, manager, make_stock, make_event, downtown, uptown
):
    _, downtown_event = seed(make_stock, make_event, downtown)
    seed(make_stock, make_event, uptown, at=START + timedelta(seconds=1))
    client = as_user(manager)

    waste = client.get(REPORT, WINDOW).json()
    feed = client.get(FEED).json()

    assert ids(waste) == [str(downtown_event.pk)]
    assert ids(feed) == [str(downtown_event.pk)]
    assert waste["grand_total"] == "1"


def test_naming_store_b_is_403_with_no_rows(
    as_user, manager, make_stock, make_event, downtown, uptown
):
    seed(make_stock, make_event, downtown)
    seed(make_stock, make_event, uptown, at=START + timedelta(seconds=1))
    client = as_user(manager)

    reports = [
        client.get(REPORT, {**WINDOW, "store": str(uptown.pk)}),
        client.get(FEED, {"store": str(uptown.pk)}),
    ]

    for response in reports:
        assert response.status_code == 403
        assert response.json() == {"detail": STORE_DENIED}


def test_regional_with_no_store_sees_assignments_plus_online(
    as_user, regional, make_stock, make_event, downtown, uptown
):
    seed(make_stock, make_event, downtown)
    seed(make_stock, make_event, uptown, at=START + timedelta(seconds=1))
    seed(make_stock, make_event, None, at=START + timedelta(seconds=2))
    client = as_user(regional)

    waste = client.get(REPORT, WINDOW).json()
    feed = client.get(FEED).json()

    assert waste["count"] == 3
    assert feed["count"] == 3
    store_ids = {row["store_id"] for row in feed["results"]}
    assert store_ids == {str(downtown.pk), str(uptown.pk), None}


def test_manager_never_sees_the_online_pool(
    as_user, manager, make_stock, make_event, downtown, uptown
):
    seed(make_stock, make_event, downtown)
    seed(make_stock, make_event, None, at=START + timedelta(seconds=1))
    client = as_user(manager)

    waste = client.get(REPORT, WINDOW).json()
    feed = client.get(FEED).json()

    assert waste["count"] == 1
    assert feed["count"] == 1
    assert [row["pool"] for row in feed["results"]] == [Pool.BRANCH]


def test_naming_a_store_excludes_online_even_for_admin(
    as_user, admin, make_stock, make_event, downtown
):
    seed(make_stock, make_event, downtown)
    seed(make_stock, make_event, None, at=START + timedelta(seconds=1))
    client = as_user(admin)

    waste = client.get(REPORT, {**WINDOW, "store": str(downtown.pk)}).json()
    feed = client.get(FEED, {"store": str(downtown.pk)}).json()

    assert waste["count"] == 1
    assert feed["count"] == 1
    assert [row["pool"] for row in feed["results"]] == [Pool.BRANCH]


def test_online_row_renders_nulls(as_user, admin, make_stock, make_event):
    seed(make_stock, make_event, None)

    row = as_user(admin).get(FEED).json()["results"][0]

    assert row["pool"] == Pool.ONLINE
    assert row["store_id"] is None
    assert row["store_name"] is None


def test_unauthenticated_is_401_on_both_routes(api_client):
    assert api_client.get(REPORT, WINDOW).status_code == 401
    assert api_client.get(FEED).status_code == 401


def test_deleting_a_store_removes_its_rows_and_events(
    as_user, admin, make_stock, make_event, downtown, uptown
):
    seed(make_stock, make_event, downtown)
    seed(make_stock, make_event, uptown, at=START + timedelta(seconds=1))

    Store.objects.filter(pk=uptown.pk).delete()

    client = as_user(admin)
    waste = client.get(REPORT, WINDOW).json()
    feed = client.get(FEED).json()

    assert StockEvent.objects.filter(store_id=uptown.pk).count() == 0
    assert Stock.objects.filter(store_id=uptown.pk).count() == 0
    assert str(uptown.pk) not in {row["store_id"] for row in waste["results"]}
    assert str(uptown.pk) not in {row["store_id"] for row in feed["results"]}


@pytest.mark.parametrize("role", list(User.Role))
def test_every_role_gets_200_on_both_routes(
    as_user, make_user, make_stock, make_event, downtown, role
):
    seed(make_stock, make_event, downtown)
    client = as_user(make_user(role=role, stores=[downtown]))

    assert client.get(REPORT, WINDOW).status_code == 200
    assert client.get(FEED).status_code == 200


def test_role_gate_exists(
    as_user, admin, make_stock, make_event, downtown, monkeypatch
):
    seed(make_stock, make_event, downtown)
    client = as_user(admin)
    monkeypatch.setitem(ROLE_ACTIONS, "stock.read", set())

    reports = [client.get(REPORT, WINDOW), client.get(FEED)]

    for response in reports:
        assert response.status_code == 403
        assert response.json() == {"detail": ROLE_DENIED}


def test_derived_discrepancy_stays_in_services():
    root = Path(__file__).resolve().parents[1] / "src" / "apps" / "inventory"
    source = root / "services.py"
    offenders = [
        f"{path.name}:{number}"
        for path in sorted(root.glob("*.py"))
        if path.name != source.name
        for number, line in enumerate(path.read_text().splitlines(), 1)
        if "derived_discrepancy" in line
    ]

    assert offenders == []
    assert "derived_discrepancy" in source.read_text()
