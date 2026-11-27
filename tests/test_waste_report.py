"""US1: the waste report over an inclusive range, with exact totals."""

import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from apps.identity.models import User
from apps.inventory.models import EventKind, Movement, StockEvent
from apps.inventory.services import waste_totals

pytestmark = pytest.mark.django_db

REPORT = "/api/stock/waste/"
START = datetime(2026, 11, 24, 0, 0, tzinfo=UTC)
END = datetime(2026, 11, 24, 23, 59, 59, 999000, tzinfo=UTC)
INVERTED_MESSAGE = "The end must not be earlier than the start."


def iso(instant: datetime) -> str:
    return instant.isoformat().replace("+00:00", "Z")


@pytest.fixture
def admin(as_user, make_user):
    return as_user(make_user(role=User.Role.ADMIN))


@pytest.fixture
def window():
    return {"start": iso(START), "end": iso(END)}


# The aggregate proof, before anything depends on it


def test_totals_are_exact_decimals(make_stock, make_event):
    stock = make_stock()
    make_event(stock, type=Movement.WASTE, quantity=Decimal("2.5"))
    make_event(stock, type=Movement.WASTE, quantity=Decimal("0.25"))

    totals = waste_totals(StockEvent.objects.all())

    assert totals[0]["total"] == Decimal("2.75")
    assert isinstance(totals[0]["total"], Decimal)


# The range and row rules


def test_both_bounds_are_inclusive(admin, make_stock, make_event, window):
    stock = make_stock()
    make_event(stock, type=Movement.WASTE, at=START)
    make_event(stock, type=Movement.WASTE, at=END)
    make_event(stock, type=Movement.WASTE, at=START - timedelta(milliseconds=1))
    make_event(stock, type=Movement.WASTE, at=END + timedelta(milliseconds=1))

    body = admin.get(REPORT, window).json()

    assert body["count"] == 2
    assert [row["at"] for row in body["results"]] == [iso(END), iso(START)]


def test_one_instant_window(admin, make_stock, make_event):
    stock = make_stock()
    make_event(stock, type=Movement.WASTE, at=START)
    make_event(stock, type=Movement.WASTE, at=START + timedelta(seconds=1))

    body = admin.get(REPORT, {"start": iso(START), "end": iso(START)}).json()

    assert body["count"] == 1
    assert body["results"][0]["at"] == iso(START)


def test_only_waste_appears(admin, make_stock, make_event, window):
    stock = make_stock()
    make_event(stock, type=Movement.RECEIVED)
    make_event(stock, type=Movement.SOLD)
    make_event(
        stock, kind=EventKind.COUNT, type=None, quantity=None, counted=Decimal(4)
    )
    make_event(stock, type=Movement.WASTE, quantity=Decimal("0.5"))

    body = admin.get(REPORT, window).json()

    assert body["count"] == 1
    assert [row["type"] for row in body["results"]] == [Movement.WASTE]
    assert len(body["totals"]) == 1
    assert body["grand_total"] == "0.5"


def test_empty_range_is_not_an_error(admin, window):
    response = admin.get(REPORT, window)
    body = response.json()

    assert response.status_code == 200
    assert body["count"] == 0
    assert body["results"] == []
    assert body["totals"] == []
    assert body["grand_total"] == "0"


def test_renamed_item_reads_current_name(
    admin, make_product, make_stock, make_event, window
):
    product = make_product(name="Milk", unit="L")
    stock = make_stock(product=product)
    make_event(stock, type=Movement.WASTE)
    product.name = "Oat milk"
    product.save()

    row = admin.get(REPORT, window).json()["results"][0]

    assert row["product_name"] == "Oat milk"
    assert row["unit"] == "L"


def test_deleted_actor_still_renders_a_name(
    admin, make_user, make_stock, make_event, window
):
    actor = make_user(role=User.Role.BARISTA)
    actor_id = str(actor.pk)
    stock = make_stock()
    make_event(stock, type=Movement.WASTE, by_id=actor.pk, by_name="Ana Silva")
    actor.delete()

    row = admin.get(REPORT, window).json()["results"][0]

    assert row["by_name"] == "Ana Silva"
    assert row["by_id"] == actor_id


# The totals rules


def test_totals_one_row_per_item(admin, make_product, make_stock, make_event, window):
    first = make_stock(product=make_product())
    second = make_stock(product=make_product())
    make_event(first, type=Movement.WASTE, quantity=Decimal(2))
    make_event(first, type=Movement.WASTE, quantity=Decimal("0.5"))
    make_event(second, type=Movement.WASTE, quantity=Decimal(7))

    totals = admin.get(REPORT, window).json()["totals"]

    assert len(totals) == 2
    by_product = {row["product_id"]: row for row in totals}
    assert by_product[str(first.product_id)]["events"] == 2
    assert by_product[str(first.product_id)]["total"] == "2.5"
    assert by_product[str(second.product_id)]["events"] == 1
    assert by_product[str(second.product_id)]["total"] == "7"


def test_totals_order(admin, make_product, make_stock, make_event, window):
    small = make_stock(product=make_product())
    large = make_stock(product=make_product())
    make_event(small, type=Movement.WASTE, quantity=Decimal(1))
    make_event(large, type=Movement.WASTE, quantity=Decimal(5))

    totals = admin.get(REPORT, window).json()["totals"]

    assert [row["product_id"] for row in totals] == [
        str(large.product_id),
        str(small.product_id),
    ]


def test_totals_break_a_tie_by_product_id(
    admin, make_product, make_stock, make_event, window
):
    first = make_stock(product=make_product())
    second = make_stock(product=make_product())
    make_event(first, type=Movement.WASTE, quantity=Decimal(3))
    make_event(second, type=Movement.WASTE, quantity=Decimal(3))

    totals = admin.get(REPORT, window).json()["totals"]

    expected = [str(pk) for pk in sorted([first.product_id, second.product_id])]
    assert [row["product_id"] for row in totals] == expected


def test_totals_cover_the_range_not_the_page(
    admin, make_product, make_stock, make_events, window
):
    big = make_stock(product=make_product())
    small = make_stock(product=make_product())
    make_events(20, stock=big, type=Movement.WASTE, quantity=Decimal(1))
    make_events(5, stock=small, type=Movement.WASTE, quantity=Decimal(1))

    params = {**window, "page_size": "10"}
    first = admin.get(REPORT, params).json()
    second = admin.get(REPORT, {**params, "page": "2"}).json()
    third = admin.get(REPORT, {**params, "page": "3"}).json()

    assert len(first["results"]) == 10
    assert first["count"] == 25
    assert sum(row["events"] for row in first["totals"]) == 25
    assert first["totals"] == second["totals"] == third["totals"]
    assert first["grand_total"] == "25"
    ids = {row["id"] for page in (first, second, third) for row in page["results"]}
    assert len(ids) == 25


def test_item_filter_narrows_rows_and_totals(
    admin, make_product, make_stock, make_event, window
):
    kept = make_stock(product=make_product())
    other = make_stock(product=make_product())
    make_event(kept, type=Movement.WASTE, quantity=Decimal(2))
    make_event(other, type=Movement.WASTE, quantity=Decimal(9))

    body = admin.get(REPORT, {**window, "product": str(kept.product_id)}).json()

    assert body["count"] == 1
    assert [row["product_id"] for row in body["results"]] == [str(kept.product_id)]
    assert [row["product_id"] for row in body["totals"]] == [str(kept.product_id)]
    assert body["grand_total"] == "2"


def test_grand_total_equals_the_totals_exactly(
    admin, make_product, make_stock, make_event, window
):
    stock = make_stock(product=make_product())
    other = make_stock(product=make_product())
    make_event(stock, type=Movement.WASTE, quantity=Decimal("2.5"))
    make_event(stock, type=Movement.WASTE, quantity=Decimal("0.25"))
    make_event(other, type=Movement.WASTE, quantity=Decimal("1.125"))

    body = admin.get(REPORT, window).json()

    summed = sum((Decimal(row["total"]) for row in body["totals"]), Decimal(0))
    assert summed - Decimal(body["grand_total"]) == 0
    assert body["grand_total"] == "3.875"


def test_events_sum_to_count(admin, make_stock, make_events, window):
    first = make_stock()
    second = make_stock()
    make_events(3, stock=first, type=Movement.WASTE)
    make_events(4, stock=second, type=Movement.WASTE)

    body = admin.get(REPORT, window).json()

    assert sum(row["events"] for row in body["totals"]) == body["count"] == 7


# The refusals and the timing bound


@pytest.mark.parametrize(
    ("params", "field", "message"),
    [
        ({"end": iso(END)}, "start", "This field is required."),
        ({"start": iso(START)}, "end", "This field is required."),
        (
            {"start": iso(END), "end": iso(START)},
            "end",
            INVERTED_MESSAGE,
        ),
        (
            {"start": "not-a-date", "end": iso(END)},
            "start",
            "Datetime has wrong format.",
        ),
        (
            {"start": iso(START), "end": iso(END), "product": "nope"},
            "product",
            "Enter a valid ObjectId.",
        ),
        (
            {"start": iso(START), "end": iso(END), "store": "nope"},
            "store",
            "Enter a valid ObjectId.",
        ),
    ],
)
def test_refusals(admin, params, field, message):
    response = admin.get(REPORT, params)

    assert response.status_code == 400
    assert response.json()[field][0].startswith(message)


def test_page_past_the_end_is_404(admin, make_stock, make_event, window):
    make_event(make_stock(), type=Movement.WASTE)

    response = admin.get(REPORT, {**window, "page": "99"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Invalid page."


def test_ten_thousand_events_under_one_second(
    admin, make_product, make_stock, make_events, window
):
    stock = make_stock(product=make_product())
    step = timedelta(minutes=10)
    make_events(3000, stock=stock, type=Movement.WASTE, quantity=Decimal(1), step=step)
    make_events(
        7000, stock=stock, type=Movement.RECEIVED, quantity=Decimal(1), step=step
    )
    params = {
        "start": iso(START),
        "end": iso(START + timedelta(days=30)),
        "page_size": "100",
    }

    started = time.perf_counter()
    response = admin.get(REPORT, params)
    elapsed = time.perf_counter() - started
    print(f"waste report over 10,000 events: {elapsed:.3f}s")

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["count"] == 3000
    assert len(body["results"]) == 100
    assert elapsed < 1.0


# US3: the two filters, alone and together


def test_store_filter_alone(admin, make_store, make_stock, make_event, window):
    kept_store = make_store(name="Downtown")
    other_store = make_store(name="Uptown")
    kept = make_stock(store=kept_store)
    elsewhere = make_stock(store=other_store)
    make_event(kept, type=Movement.WASTE, quantity=Decimal(2))
    make_event(elsewhere, type=Movement.WASTE, quantity=Decimal(9))

    body = admin.get(REPORT, {**window, "store": str(kept_store.pk)}).json()

    assert body["count"] == 1
    assert [row["store_id"] for row in body["results"]] == [str(kept_store.pk)]
    assert [row["product_id"] for row in body["totals"]] == [str(kept.product_id)]
    assert body["grand_total"] == "2"


def test_store_and_item_together(admin, make_store, make_stock, make_event, window):
    kept_store = make_store(name="Downtown")
    other_store = make_store(name="Uptown")
    kept = make_stock(store=kept_store)
    same_product_elsewhere = make_stock(store=other_store, product=kept.product)
    other_item_same_store = make_stock(store=kept_store)
    make_event(kept, type=Movement.WASTE, quantity=Decimal(3))
    make_event(same_product_elsewhere, type=Movement.WASTE, quantity=Decimal(4))
    make_event(other_item_same_store, type=Movement.WASTE, quantity=Decimal(5))

    body = admin.get(
        REPORT,
        {**window, "store": str(kept_store.pk), "product": str(kept.product_id)},
    ).json()

    assert body["count"] == 1
    assert body["results"][0]["stock_id"] == str(kept.pk)
    assert len(body["totals"]) == 1
    assert body["grand_total"] == "3"


def test_item_with_no_events_answers_empty(
    admin, make_product, make_stock, make_store, window
):
    make_stock(store=make_store())
    silent = make_product()

    response = admin.get(REPORT, {**window, "product": str(silent.pk)})
    body = response.json()

    assert response.status_code == 200
    assert body["count"] == 0
    assert body["totals"] == []
    assert body["grand_total"] == "0"
