"""The refusal rules, in one place.

These functions raise; the caller owns the transaction. That way a 400 aborts the
transaction and no number moves, which is what FR-024 asks for.
"""

from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from .models import Movement, Pool

POOL_ERROR = "A branch pool needs a store and the online pool forbids one."
QUANTITY_ERROR = "The quantity must be greater than zero with at most 3 decimal places."
COUNTED_ERROR = (
    "The counted number must be zero or greater with at most 3 decimal places."
)
NOTE_ERROR = "Waste needs a note."
SOLD_BRANCH_ERROR = "A sale cannot be recorded in a store pool yet."
FUTURE_ERROR = "The instant cannot be in the future."
BACKDATED_ERROR = "The instant is earlier than the newest count of this stock."

SMALLEST = Decimal("0.001")


def validate_pool(pool_type, store_id) -> None:
    """A branch pool owns a store, and the online pool owns nothing (FR-002)."""
    if store_id is None:
        if pool_type != Pool.ONLINE:
            raise serializers.ValidationError({"store": [POOL_ERROR]})
        return
    if pool_type == Pool.ONLINE:
        raise serializers.ValidationError({"store": [POOL_ERROR]})


def validate_quantity(value: Decimal, *, allow_zero: bool = False) -> None:
    """Positive (or zero for a count), finite, and no finer than thousandths."""
    message = COUNTED_ERROR if allow_zero else QUANTITY_ERROR
    if value < 0 or (value == 0 and not allow_zero):
        raise serializers.ValidationError({"quantity": [message]})
    if value != value.quantize(SMALLEST):
        raise serializers.ValidationError({"quantity": [message]})


def validate_note(movement_type, note) -> None:
    """Waste carries a reason, because M3 reports on it (FR-012)."""
    if movement_type == Movement.WASTE and not (note or "").strip():
        raise serializers.ValidationError({"note": [NOTE_ERROR]})


def validate_movement_type(movement_type, pool_type) -> None:
    """No point of sale exists, so a store pool cannot record a sale.

    This is a milestone policy and it lives in this one rule. It must not become
    a storage constraint, a per-pool list of allowed types, or an index, so that
    a future point of sale lifts it with no migration (FR-013).
    """
    if movement_type == Movement.SOLD and pool_type == Pool.BRANCH:
        raise serializers.ValidationError({"type": [SOLD_BRANCH_ERROR]})


def validate_instant(at, last_count_at) -> None:
    """No future write, and nothing that predates the baseline (FR-014)."""
    if at > timezone.now():
        raise serializers.ValidationError({"at": [FUTURE_ERROR]})
    if last_count_at is not None and at < last_count_at:
        raise serializers.ValidationError({"at": [BACKDATED_ERROR]})
