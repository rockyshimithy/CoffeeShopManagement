from bson import ObjectId
from django.db.models import F
from django_mongodb_backend.transaction import atomic
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from apps.identity.permissions import (
    ROLE_DENIED,
    can,
    require_action,
    require_store_access,
    scope_store_ids,
)
from apps.identity.services import employee_store_ids
from apps.stores.services import store_exists
from core.transactions import retry_on_conflict

from .cache import read_snapshot, schedule_key, write_snapshot
from .models import ScheduleRevision, Shift
from .serializers import ShiftSerializer, ShiftWriteSerializer
from .validators import validate_shift_window


def schedule(actor, store_id, window, page: int, page_size: int) -> dict:
    """One page of the schedule for the stores the actor may see.

    A hit is answered from the stored page, so no join, sort, or name
    resolution runs. A miss runs the aggregation once and stores the page.
    """
    store_ids = scope_store_ids(actor, store_id)
    key = schedule_key(store_ids, window, page, page_size)

    cached = read_snapshot(key)
    if cached is not None:
        return cached

    queryset = (
        Shift.objects.filter(
            store_id__in=store_ids,
            starts_at__gte=window[0],
            starts_at__lt=window[1],
        )
        .select_related("employee__user", "store")
        .order_by(
            "starts_at",
            "employee__user__first_name",
            "employee__user__last_name",
            "id",
        )
    )
    count = queryset.count()
    offset = (page - 1) * page_size
    rows = queryset[offset : offset + page_size]
    body = {"count": count, "results": ShiftSerializer(rows, many=True).data}
    write_snapshot(key, body)
    return body


def create_shift(actor, data: dict) -> Shift:
    """Insert one shift, refusing everything FR-003 to FR-008 refuses.

    The employee read, the revision bump, the overlap check, and the insert all
    share one transaction. The bump is what makes two concurrent creates for the
    same employee collide, so the second one re-reads and answers 400.
    """
    if not can(actor, "shift.create"):
        raise PermissionDenied(ROLE_DENIED)
    serializer = ShiftWriteSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    fields = dict(serializer.validated_data)
    employee_id = fields["employee_id"]
    store_id = fields["store_id"]
    require_store_access(actor, store_id)

    def operation():
        with atomic():
            if not store_exists(store_id):
                raise serializers.ValidationError(
                    {"store_id": ["No store exists with this id."]}
                )
            stores = employee_store_ids(employee_id)
            if stores is None:
                raise serializers.ValidationError(
                    {"employee_id": ["No employee profile exists with this id."]}
                )
            if store_id not in stores:
                raise serializers.ValidationError(
                    {"store_id": ["This employee is not assigned to this store."]}
                )
            bump_store_revisions(stores)
            validate_shift_window(employee_id, fields["starts_at"], fields["ends_at"])
            return Shift.objects.create(**fields)

    return retry_on_conflict(operation)


def update_shift(actor, shift: Shift, data: dict) -> Shift:
    """Change the two instants of one shift, and nothing else (FR-010)."""
    require_action(actor, "shift.change", shift.store_id)
    _refuse_identity_change(data)

    serializer = ShiftWriteSerializer(data=data, partial=True)
    serializer.is_valid(raise_exception=True)
    starts_at = serializer.validated_data.get("starts_at", shift.starts_at)
    ends_at = serializer.validated_data.get("ends_at", shift.ends_at)
    employee_id = shift.employee_id
    shift_id = shift.pk

    def operation():
        with atomic():
            stores = employee_store_ids(employee_id) or []
            bump_store_revisions(stores)
            validate_shift_window(employee_id, starts_at, ends_at, exclude_pk=shift_id)
            Shift.objects.filter(pk=shift_id).update(
                starts_at=starts_at, ends_at=ends_at
            )
            return Shift.objects.get(pk=shift_id)

    return retry_on_conflict(operation)


def delete_shift(actor, shift: Shift) -> None:
    """Remove one shift and move the cache token of its store.

    No overlap guard is needed here, and no other store is touched: a delete
    cannot create a conflict, and the shift only ever appeared in its own
    store's schedule.
    """
    require_action(actor, "shift.delete", shift.store_id)
    shift_id = shift.pk
    store_id = shift.store_id

    def operation():
        with atomic():
            bump_store_revisions([store_id])
            Shift.objects.filter(pk=shift_id).delete()

    return retry_on_conflict(operation)


def shift_store_ids(employee_id) -> list[ObjectId]:
    """Public read for identity: the stores where one profile holds shifts."""
    rows = Shift.objects.filter(employee_id=employee_id).values_list(
        "store_id", flat=True
    )
    return list(set(rows))


def bump_store_revisions(store_ids) -> None:
    """Move the write guard and the cache token of every store in the list.

    Called inside the caller's transaction. A missing row is created, and a
    concurrent create that loses the race raises a duplicate key error, which is
    a ``DatabaseError``, so the caller's ``retry_on_conflict`` replays and takes
    the update path.
    """
    for store_id in store_ids:
        bumped = ScheduleRevision.objects.filter(store_id=store_id).update(
            revision=F("revision") + 1
        )
        if not bumped:
            ScheduleRevision.objects.create(store_id=store_id, revision=1)


def _refuse_identity_change(data: dict) -> None:
    """A shift's employee and store are fixed. Changing them is delete plus create."""
    errors = {}
    if "employee_id" in data:
        errors["employee_id"] = [
            "A shift's employee cannot change. Delete the shift and create a new one."
        ]
    if "store_id" in data:
        errors["store_id"] = [
            "A shift's store cannot change. Delete the shift and create a new one."
        ]
    if errors:
        raise serializers.ValidationError(errors)
