from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .models import Shift

MAX_SHIFT = timedelta(hours=12)


def validate_shift_window(employee_id, starts_at, ends_at, *, exclude_pk=None) -> None:
    """Apply FR-003 to FR-006 to one shift, excluding ``exclude_pk`` from the check.

    The overlap query is not atomic by itself. The caller runs it inside the
    transaction that bumps the employee's store revisions, which is what forces
    two concurrent writes to conflict (FR-009).
    """
    if ends_at <= starts_at:
        raise serializers.ValidationError(
            {"ends_at": ["The end must be later than the start."]}
        )

    same_day = (
        timezone.localtime(starts_at).date() == timezone.localtime(ends_at).date()
    )
    if not same_day:
        raise serializers.ValidationError(
            {"ends_at": ["A shift cannot cross midnight."]}
        )

    if ends_at - starts_at > MAX_SHIFT:
        raise serializers.ValidationError(
            {"ends_at": ["A shift cannot last more than 12 hours."]}
        )

    conflict = Shift.objects.filter(
        employee_id=employee_id,
        starts_at__lt=ends_at,
        ends_at__gt=starts_at,
    )
    if exclude_pk is not None:
        conflict = conflict.exclude(pk=exclude_pk)
    if conflict.exists():
        raise serializers.ValidationError(
            {"starts_at": ["This shift overlaps another shift for the same employee."]}
        )
