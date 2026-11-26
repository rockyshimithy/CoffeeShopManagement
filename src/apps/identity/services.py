from bson import ObjectId
from django.db.models import F, Q, QuerySet
from django.http import Http404
from django_mongodb_backend.transaction import atomic
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from core.transactions import retry_on_conflict

from .models import AdminGuard, Employee, User
from .permissions import (
    ACCOUNT_MANAGED_ROLES,
    LAST_ADMIN_DENIED,
    ROLE_DENIED,
    can,
    require_account_change,
    require_user_in_scope,
    scope_stores,
)
from .serializers import AccountWriteSerializer, EmployeeSerializer

ADMIN_GUARD_KEY = "last-admin"


def create_account(actor: User, data: dict) -> User:
    """Create a staff account inside the actor's role and store limits."""
    serializer = AccountWriteSerializer(data=data, context={"actor": actor})
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    if user.role == User.Role.REGIONAL_MANAGER:
        assign_all_stores_to_regional_manager(user)
        user.refresh_from_db()
    return user


def update_account(actor: User, user: User, data: dict) -> User:
    """Change one account, guarding the last admin and the actor's limits.

    The guard reads a count and the save writes, so both run in one transaction
    with the guard row bumped first. That is what stops two concurrent removals
    from leaving zero admins (FR-027).
    """
    require_account_change(actor, user)
    serializer = AccountWriteSerializer(
        user, data=data, partial=True, context={"actor": actor}
    )
    serializer.is_valid(raise_exception=True)
    new_role = serializer.validated_data.get("role", user.role)
    new_is_active = serializer.validated_data.get("is_active", user.is_active)
    keeps_admin = new_role == User.Role.ADMIN and new_is_active
    user_id = user.pk

    def operation():
        with atomic():
            target = User.objects.filter(pk=user_id).first()
            if target is None:
                raise Http404
            _take_admin_slot()
            ensure_admin_remains(target, keeps_admin=keeps_admin)
            saved = serializer.save()
            if saved.role == User.Role.REGIONAL_MANAGER:
                assign_all_stores_to_regional_manager(saved)
            return saved

    saved = retry_on_conflict(operation)
    saved.refresh_from_db()
    return saved


def create_employee(actor: User, data: dict) -> Employee:
    """Attach an employee profile to an account the actor may reach."""
    if not can(actor, "employee.create"):
        raise PermissionDenied(ROLE_DENIED)
    serializer = EmployeeSerializer(data=data, context={"actor": actor})
    serializer.is_valid(raise_exception=True)
    user = User.objects.filter(pk=serializer.validated_data["user_id"]).first()
    if user is None:
        raise serializers.ValidationError(
            {"user_id": ["No account exists with this id."]}
        )
    if Employee.objects.filter(user_id=user.pk).exists():
        raise serializers.ValidationError(
            {"user_id": ["This account already has an employee profile."]}
        )
    require_user_in_scope(actor, user)
    return Employee.objects.create(
        user_id=user.pk, hire_date=serializer.validated_data["hire_date"]
    )


def update_employee(actor: User, employee: Employee, data: dict) -> Employee:
    """Change the hire date, after the same reach check as creation."""
    if not can(actor, "employee.change"):
        raise PermissionDenied(ROLE_DENIED)
    require_user_in_scope(actor, employee.user)
    serializer = EmployeeSerializer(
        employee, data=data, partial=True, context={"actor": actor}
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return employee


def visible_employees(actor: User) -> QuerySet[Employee]:
    """Profiles the actor may list, scoped through the linked account's stores."""
    queryset = Employee.objects.select_related("user")
    if actor.role in (User.Role.ADMIN, User.Role.REGIONAL_MANAGER):
        return queryset
    if actor.role not in (User.Role.MANAGER, User.Role.SUPERVISOR, User.Role.BARISTA):
        raise PermissionDenied(ROLE_DENIED)
    return queryset.filter(user__store_ids__overlap=actor.store_ids)


def visible_accounts(actor: User) -> QuerySet[User]:
    """The accounts an actor may list: all for admin and regional, own store
    staff plus self for a manager."""
    if actor.role in (User.Role.ADMIN, User.Role.REGIONAL_MANAGER):
        return User.objects.all()
    if actor.role != User.Role.MANAGER:
        raise PermissionDenied(ROLE_DENIED)
    scoped = scope_stores(User.objects.all(), actor, field="store_ids", overlap=True)
    return scoped.filter(Q(role__in=ACCOUNT_MANAGED_ROLES) | Q(pk=actor.pk))


def employee_store_ids(employee_id: ObjectId) -> list[ObjectId] | None:
    """Public read for workforce: the stores one employee profile belongs to.

    ``None`` means no profile has that id. The stores come from the linked
    account, which is the single source of scope for a person. Two plain finds
    instead of a join, so this stays usable inside a transaction.
    """
    user_id = (
        Employee.objects.filter(pk=employee_id)
        .values_list("user_id", flat=True)
        .first()
    )
    if user_id is None:
        return None
    store_ids = (
        User.objects.filter(pk=user_id).values_list("store_ids", flat=True).first()
    )
    return list(store_ids or [])


def _update_store_ids(user_id: ObjectId, store_ids: list[ObjectId]) -> None:
    User.objects.filter(pk=user_id).update(store_ids=store_ids)


def add_store_to_regional_managers(store_id: ObjectId) -> None:
    """Append a new store to every regional manager.

    The write replaces the whole list, so the read and the write must share one
    transaction. That transaction opens here, not in the caller: MongoDB aborts
    one of two conflicting writes with a ``DatabaseError`` instead of dropping an
    append, and the caller retries.
    """
    rows = User.objects.filter(role=User.Role.REGIONAL_MANAGER).values_list(
        "pk", "store_ids"
    )
    with atomic():
        for user_id, store_ids in rows:
            if store_id not in store_ids:
                _update_store_ids(user_id, [*store_ids, store_id])


def remove_store_from_all_users(store_id: ObjectId) -> None:
    """Remove a deleted store from every account, inside one transaction."""
    rows = User.objects.filter(store_ids__contains=[store_id]).values_list(
        "pk", "store_ids"
    )
    with atomic():
        for user_id, store_ids in rows:
            remaining = [known for known in store_ids if known != store_id]
            if len(remaining) != len(store_ids):
                _update_store_ids(user_id, remaining)


def assign_all_stores_to_regional_manager(user: User) -> None:
    from apps.stores.services import all_store_ids

    _update_store_ids(user.pk, list(all_store_ids()))


def ensure_admin_remains(user: User, *, keeps_admin: bool) -> None:
    """Refuse to remove the only active admin from the admin role.

    Must be called inside the transaction that already took the admin slot, so
    the count cannot be stale against a concurrent removal.
    """
    if user.role != User.Role.ADMIN or not user.is_active:
        return
    if keeps_admin:
        return
    # exists() and not count(): this backend compiles count() with a $unionWith
    # stage, which MongoDB refuses inside a multi-document transaction.
    others = (
        User.objects.filter(role=User.Role.ADMIN, is_active=True)
        .exclude(pk=user.pk)
        .exists()
    )
    if not others:
        raise PermissionDenied(LAST_ADMIN_DENIED)


def _take_admin_slot() -> None:
    """Bump the one row every admin-removing transaction writes.

    A concurrent create that loses the race raises a duplicate key error, which
    is a ``DatabaseError``, so the caller's ``retry_on_conflict`` replays and
    takes the update path.
    """
    bumped = AdminGuard.objects.filter(key=ADMIN_GUARD_KEY).update(
        revision=F("revision") + 1
    )
    if not bumped:
        AdminGuard.objects.create(key=ADMIN_GUARD_KEY)


def delete_account(actor: User, user: User) -> None:
    """Delete an account, its employee profile, and that profile's shifts.

    The profile and the shifts leave through the cascades declared on the
    models. The store revisions are bumped by hand, because a cascade writes no
    revision and a cached schedule would otherwise keep naming the deleted
    person.
    """
    if not can(actor, "account.delete"):
        raise PermissionDenied(ROLE_DENIED)
    user_id = user.pk

    def operation():
        with atomic():
            target = User.objects.filter(pk=user_id).first()
            if target is None:
                raise Http404
            _take_admin_slot()
            ensure_admin_remains(target, keeps_admin=False)
            _bump_stores_of_deleted_shifts(user_id)
            User.objects.filter(pk=user_id).delete()

    return retry_on_conflict(operation)


def _bump_stores_of_deleted_shifts(user_id: ObjectId) -> None:
    """Move the cache token of every store that is about to lose a shift."""
    from apps.workforce.services import bump_store_revisions, shift_store_ids

    profile = Employee.objects.filter(user_id=user_id).first()
    if profile is None:
        return
    store_ids = shift_store_ids(profile.pk)
    if store_ids:
        bump_store_revisions(store_ids)
