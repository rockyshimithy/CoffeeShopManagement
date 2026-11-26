"""The single write path for stock, plus the reads the endpoints need.

``record`` is the only function in the project that writes ``Stock`` or
``StockEvent``. It opens one transaction, applies the number with a targeted
update, and appends the event, so the two can never disagree (FR-024, I4).
"""

from django.db import DatabaseError
from django.db.models import F, Q
from django.utils import timezone
from django_mongodb_backend.transaction import atomic
from rest_framework import serializers
from rest_framework.exceptions import APIException

from apps.catalog.services import product_exists, product_labels, product_thresholds
from apps.identity.permissions import (
    reaches_every_store,
    require_action,
    require_stock_access,
    scope_store_ids,
)
from apps.stores.services import store_exists, store_names
from core.transactions import retry_on_conflict

from .models import EventKind, Movement, Pool, Stock, StockEvent
from .serializers import CountWriteSerializer, MovementWriteSerializer
from .validators import (
    validate_instant,
    validate_movement_type,
    validate_note,
    validate_pool,
    validate_quantity,
)

STOCK_ATTEMPTS = 3
SUBTRACTING = frozenset({Movement.SOLD, Movement.WASTE})

NOT_FOUND_PRODUCT = "No product exists with this id."
NOT_FOUND_STORE = "No store exists with this id."
OVERDRAW = "There is not enough stock for this movement. Record a count first."
CONFLICT = (
    "The stock changed while this write was being applied. "
    "Nothing was saved. Try again."
)


class StockConflict(APIException):
    """Three lost write conflicts in a row. Nothing was applied, so resending is safe.

    The server stops after three rounds. ``wait`` becomes ``Retry-After: 1``, which
    hands the next round to the client without spending a connection here. One
    second is the header's smallest unit, not a measurement: the conflict clears in
    milliseconds, and a client that resends sooner is also safe.
    """

    status_code = 409
    wait = 1  # DRF's exception handler renders this as Retry-After
    default_detail = CONFLICT
    default_code = "stock_conflict"


def stock_scope(queryset, actor, store_id=None):
    """Limit a stock queryset to what the actor may see.

    A branch pool is a store, so the store assignment decides it. The online pool
    has no store, so it is reachable only by an actor whose assignments already
    cover every store. Both answers come from ``identity.permissions``, so no role
    comparison exists here (SC-006).
    """
    store_ids = scope_store_ids(actor, store_id)
    if store_id is None and reaches_every_store(actor):
        return queryset.filter(Q(store_id__in=store_ids) | Q(store_id__isnull=True))
    return queryset.filter(store_id__in=store_ids)


def enrich(rows) -> dict:
    """The lookups one page of stock rows needs, batched after pagination.

    Two queries per page instead of two per row, which is the rule that replaces
    ``prefetch_related()`` on this backend.
    """
    rows = list(rows)
    product_ids = [row.product_id for row in rows]
    return {
        "labels": product_labels(product_ids),
        "thresholds": product_thresholds(product_ids),
        "store_names": store_names([row.store_id for row in rows]),
    }


def record_movement(actor, data: dict) -> StockEvent:
    """Record a delivery, a sale, or waste."""
    serializer = MovementWriteSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return _record(actor, kind=EventKind.MOVEMENT, **serializer.validated_data)


def record_count(actor, data: dict) -> StockEvent:
    """Record an observation of the shelf."""
    serializer = CountWriteSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return _record(actor, kind=EventKind.COUNT, **serializer.validated_data)


def _record(
    actor,
    *,
    kind,
    product_id,
    pool_type,
    store_id,
    movement_type=None,
    quantity=None,
    counted=None,
    note="",
    at=None,
) -> StockEvent:
    """The one write. Every branch below ends in one update and one event."""
    require_action(actor, "stock.record")
    require_stock_access(actor, store_id)
    validate_pool(pool_type, store_id)
    if kind == EventKind.MOVEMENT:
        validate_movement_type(movement_type, pool_type)
        validate_quantity(quantity)
        validate_note(movement_type, note)
    else:
        validate_quantity(counted, allow_zero=True)

    instant = at or timezone.now()
    by_name = _display_name(actor)

    if not product_exists(product_id):
        raise serializers.ValidationError({"product": [NOT_FOUND_PRODUCT]})
    if store_id is not None and not store_exists(store_id):
        raise serializers.ValidationError({"store": [NOT_FOUND_STORE]})

    def operation():
        with atomic():
            row = Stock.objects.filter(
                product_id=product_id, pool_type=pool_type, store_id=store_id
            ).first()
            if row is None:
                row = Stock.objects.create(
                    product_id=product_id, pool_type=pool_type, store_id=store_id
                )
            stock_pk = row.pk

            validate_instant(instant, row.last_count_at)

            if kind == EventKind.COUNT:
                Stock.objects.filter(pk=stock_pk).update(
                    current_stock=counted,
                    last_count=counted,
                    last_count_at=instant,
                    last_event_at=instant,
                )
            elif movement_type in SUBTRACTING:
                updated = Stock.objects.filter(
                    pk=stock_pk, current_stock__gte=quantity
                ).update(
                    current_stock=F("current_stock") - quantity,
                    last_event_at=instant,
                )
                if not updated:
                    raise serializers.ValidationError({"quantity": [OVERDRAW]})
            else:
                Stock.objects.filter(pk=stock_pk).update(
                    current_stock=F("current_stock") + quantity,
                    last_event_at=instant,
                )

            return StockEvent.objects.create(
                stock_id=stock_pk,
                product_id=product_id,
                pool_type=pool_type,
                store_id=store_id,
                kind=kind,
                type=movement_type,
                quantity=quantity,
                counted=counted,
                by_id=actor.pk,
                by_name=by_name,
                at=instant,
                note=note,
            )

    try:
        return retry_on_conflict(operation, attempts=STOCK_ATTEMPTS)
    except DatabaseError as exc:
        raise StockConflict() from exc


def _display_name(actor) -> str:
    name = f"{actor.first_name} {actor.last_name}".strip()
    return (name or actor.email)[:120]


def stock_after(event: StockEvent) -> Stock:
    """The row an event belongs to, read after the write inside the same request."""
    return Stock.objects.get(pk=event.stock_id)


def list_events(stock_id, page: int, page_size: int):
    """One record's history, newest first, with a stable order for equal instants."""
    queryset = StockEvent.objects.filter(stock_id=stock_id).order_by("-at", "-id")
    total = queryset.count()
    offset = (page - 1) * page_size
    return total, list(queryset[offset : offset + page_size])


def low_stock(actor, store_id, page: int, page_size: int):
    """Rows strictly below their product's threshold, worst first.

    The shortage spans two collections, so the order and the page happen here.
    A Mongo ``$lookup`` would move the sort into the database and bypass the ORM
    for one endpoint; the working set is the actor's stores times the catalog.
    """
    rows = list(stock_scope(Stock.objects.all(), actor, store_id))
    thresholds = product_thresholds([row.product_id for row in rows])
    low = []
    for row in rows:
        threshold = thresholds.get(str(row.product_id))
        if threshold is None or row.current_stock >= threshold:
            continue
        low.append((threshold - row.current_stock, row))
    low.sort(key=lambda pair: (-pair[0], str(pair[1].product_id)))
    total = len(low)
    offset = (page - 1) * page_size
    return total, [row for _, row in low[offset : offset + page_size]]


def derived_discrepancy(stock: Stock):
    """The gap the newest count closed, derived from events only (FR-019).

    ``None`` when the row has no count yet. The result is ``predicted - counted``,
    so a positive number is stock that went missing and a negative one is stock
    that was never recorded. The previous baseline is the older of the two newest
    COUNT events, and everything between them is the number the movements
    predicted.
    """
    counts = list(
        StockEvent.objects.filter(stock_id=stock.pk, kind=EventKind.COUNT).order_by(
            "-at"
        )[:2]
    )
    if not counts:
        return None
    newest = counts[0]
    if len(counts) == 1:
        baseline = 0
        window_start = None
    else:
        baseline = counts[1].counted
        window_start = counts[1].at

    movements = StockEvent.objects.filter(stock_id=stock.pk, kind=EventKind.MOVEMENT)
    if window_start is not None:
        movements = movements.filter(at__gt=window_start)
    expected = baseline
    for event in movements.values_list("type", "quantity"):
        movement_type, quantity = event
        if movement_type in SUBTRACTING:
            expected -= quantity
        else:
            expected += quantity
    return expected - newest.counted


def pool_is_visible(actor, pool_type) -> bool:
    """Whether the online pool is reachable, used by the list filter."""
    return pool_type != Pool.ONLINE or reaches_every_store(actor)
