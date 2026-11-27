"""US2: the activity feed, one timeline across items."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from apps.identity.models import User
from apps.inventory.models import EventKind, Movement

pytestmark = pytest.mark.django_db

FEED = "/api/stock/activity/"
START = datetime(2026, 11, 24, 8, 0, tzinfo=UTC)


@pytest.fixture
def admin(as_user, make_user):
    return as_user(make_user(role=User.Role.ADMIN))


def ids(body) -> list[str]:
    return [row["id"] for row in body["results"]]


def test_five_changes_newest_first(admin, make_stock, make_events):
    stock = make_stock()
    created = make_events(5, stock=stock, type=Movement.WASTE)

    body = admin.get(FEED).json()

    assert body["count"] == 5
    assert ids(body) == [str(row.pk) for row in reversed(created)]


def test_page_one_holds_the_newest_twenty(admin, make_stock, make_events):
    stock = make_stock()
    created = make_events(25, stock=stock, type=Movement.RECEIVED)

    first = admin.get(FEED).json()
    second = admin.get(FEED, {"page": "2"}).json()

    assert first["count"] == 25
    assert ids(first) == [str(row.pk) for row in reversed(created[-20:])]
    assert ids(second) == [str(row.pk) for row in reversed(created[:5])]
    assert len(set(ids(first) + ids(second))) == 25


def test_mixed_kinds_share_one_list(admin, make_stock, make_event):
    stock = make_stock()
    make_event(stock, type=Movement.RECEIVED, at=START + timedelta(seconds=1))
    make_event(
        stock,
        kind=EventKind.COUNT,
        type=None,
        quantity=None,
        counted=7,
        at=START + timedelta(seconds=4),
    )
    make_event(stock, type=Movement.SOLD, at=START + timedelta(seconds=2))
    make_event(stock, type=Movement.WASTE, at=START + timedelta(seconds=3))

    body = admin.get(FEED).json()

    assert body["count"] == 4
    assert [row["kind"] for row in body["results"]] == [
        EventKind.COUNT,
        EventKind.MOVEMENT,
        EventKind.MOVEMENT,
        EventKind.MOVEMENT,
    ]
    assert [row["type"] for row in body["results"]] == [
        None,
        Movement.WASTE,
        Movement.SOLD,
        Movement.RECEIVED,
    ]


def test_same_instant_order_is_stable_across_reads(admin, make_stock, make_event):
    stock = make_stock()
    make_event(stock, type=Movement.RECEIVED, at=START)
    make_event(stock, type=Movement.SOLD, at=START)

    first = admin.get(FEED).json()
    second = admin.get(FEED).json()

    assert ids(first) == ids(second)
    assert len(ids(first)) == 2


def test_tie_across_a_page_boundary_neither_repeats_nor_drops(
    admin, make_stock, make_event
):
    stock = make_stock()
    make_event(stock, type=Movement.RECEIVED, at=START)
    make_event(stock, type=Movement.SOLD, at=START)

    first = admin.get(FEED, {"page_size": "1"}).json()
    second = admin.get(FEED, {"page_size": "1", "page": "2"}).json()

    assert len(first["results"]) == 1
    assert len(second["results"]) == 1
    assert ids(first) != ids(second)


def test_page_size_is_capped_at_one_hundred(admin, make_stock, make_events):
    make_events(120, stock=make_stock(), type=Movement.RECEIVED)

    body = admin.get(FEED, {"page_size": "1000"}).json()

    assert len(body["results"]) == 100
    assert body["count"] == 120
    assert body["next"] is not None


def test_page_past_the_end_is_404(admin):
    response = admin.get(FEED, {"page": "99"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Invalid page."


def test_empty_scope_answers_an_empty_page(admin):
    response = admin.get(FEED)
    body = response.json()

    assert response.status_code == 200
    assert body["count"] == 0
    assert body["results"] == []
    assert body["next"] is None
    assert body["previous"] is None


def test_deleted_actor_still_renders_a_name(admin, make_user, make_stock, make_event):
    actor = make_user(role=User.Role.BARISTA)
    actor_id = str(actor.pk)
    make_event(make_stock(), type=Movement.WASTE, by_id=actor.pk, by_name="Ana Silva")
    actor.delete()

    row = admin.get(FEED).json()["results"][0]

    assert row["by_name"] == "Ana Silva"
    assert row["by_id"] == actor_id


def test_renamed_item_reads_current_name(admin, make_product, make_stock, make_event):
    product = make_product(name="Milk", unit="L")
    make_event(make_stock(product=product), type=Movement.WASTE)
    product.name = "Oat milk"
    product.save()

    row = admin.get(FEED).json()["results"][0]

    assert row["product_name"] == "Oat milk"
    assert row["unit"] == "L"
    assert row["quantity"] == "1"
    assert row["counted"] is None
    assert row["store_name"] is not None


def test_a_count_renders_counted_and_a_null_quantity(admin, make_stock, make_event):
    stock = make_stock()
    make_event(
        stock, kind=EventKind.COUNT, type=None, quantity=None, counted=Decimal("4.5")
    )

    row = admin.get(FEED).json()["results"][0]

    assert row["counted"] == "4.5"
    assert row["quantity"] is None


# US3: the two filters, alone and together


def test_item_filter_alone(admin, make_stock, make_event):
    kept = make_stock()
    other = make_stock()
    make_event(kept, type=Movement.WASTE, at=START)
    make_event(other, type=Movement.WASTE, at=START + timedelta(seconds=1))

    body = admin.get(FEED, {"product": str(kept.product_id)}).json()

    assert body["count"] == 1
    assert [row["product_id"] for row in body["results"]] == [str(kept.product_id)]


def test_store_filter_alone(admin, make_store, make_stock, make_event):
    kept_store = make_store(name="Downtown")
    other_store = make_store(name="Uptown")
    make_event(make_stock(store=kept_store), type=Movement.WASTE, at=START)
    make_event(
        make_stock(store=other_store),
        type=Movement.WASTE,
        at=START + timedelta(seconds=1),
    )

    body = admin.get(FEED, {"store": str(kept_store.pk)}).json()

    assert body["count"] == 1
    assert [row["store_id"] for row in body["results"]] == [str(kept_store.pk)]


def test_store_and_item_together(admin, make_store, make_stock, make_event):
    kept_store = make_store(name="Downtown")
    other_store = make_store(name="Uptown")
    kept = make_stock(store=kept_store)
    same_product_elsewhere = make_stock(store=other_store, product=kept.product)
    other_item_same_store = make_stock(store=kept_store)
    make_event(kept, type=Movement.WASTE, at=START)
    make_event(
        same_product_elsewhere, type=Movement.WASTE, at=START + timedelta(seconds=1)
    )
    make_event(
        other_item_same_store, type=Movement.WASTE, at=START + timedelta(seconds=2)
    )

    body = admin.get(
        FEED, {"store": str(kept_store.pk), "product": str(kept.product_id)}
    ).json()

    assert body["count"] == 1
    assert body["results"][0]["stock_id"] == str(kept.pk)


def test_item_with_no_events_answers_empty(admin, make_product):
    silent = make_product()

    response = admin.get(FEED, {"product": str(silent.pk)})

    assert response.status_code == 200
    assert response.json()["count"] == 0
    assert response.json()["results"] == []


@pytest.mark.parametrize("name", ["store", "product"])
def test_malformed_ids_answer_400(admin, name):
    response = admin.get(FEED, {name: "not-an-object-id"})

    assert response.status_code == 400
    assert "Enter a valid ObjectId." in response.content.decode()
