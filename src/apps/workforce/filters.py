from datetime import datetime, timedelta

from django.utils import timezone
from rest_framework import serializers

from core.fields import ObjectIdField

WINDOW_ERROR = "The window must start before it ends and span at most 31 days."
WEEK = timedelta(days=7)
MAX_WINDOW = timedelta(days=31)


class ScheduleQuerySerializer(serializers.Serializer):
    """The three optional filters of a schedule read.

    ``from`` is a Python keyword, so the query parameter names on the wire are
    mapped by hand in ``parse_window``.
    """

    store = ObjectIdField(required=False, allow_null=True)
    window_from = serializers.DateTimeField(required=False, allow_null=True)
    window_to = serializers.DateTimeField(required=False, allow_null=True)


def start_of_week(moment: datetime) -> datetime:
    """Monday 00:00 of the week containing ``moment``, in the project time zone."""
    local = timezone.localtime(moment)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=midnight.weekday())


def parse_window(params) -> tuple:
    """Return ``(store_id, window_from, window_to)`` for one schedule read.

    No range means the current week, one bound alone means a seven day window,
    and anything longer than 31 days or backwards is invalid.
    """
    serializer = ScheduleQuerySerializer(
        data={
            "store": params.get("store") or None,
            "window_from": params.get("from") or None,
            "window_to": params.get("to") or None,
        }
    )
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    start = data.get("window_from")
    end = data.get("window_to")
    if start is None and end is None:
        start = start_of_week(timezone.now())
        end = start + WEEK
    elif start is None:
        start = end - WEEK
    elif end is None:
        end = start + WEEK

    if end <= start or (end - start) > MAX_WINDOW:
        raise serializers.ValidationError({"detail": WINDOW_ERROR})

    return data.get("store"), start, end
