from bson import ObjectId
from django.db.models import Q, QuerySet
from django_mongodb_backend.transaction import atomic
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from .models import Employee, User
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
    """Change one account, guarding the last admin and the actor's limits."""
    require_account_change(actor, user)
    serializer = AccountWriteSerializer(
        user, data=data, partial=True, context={"actor": actor}
    )
    serializer.is_valid(raise_exception=True)
    new_role = serializer.validated_data.get("role", user.role)
    new_is_active = serializer.validated_data.get("is_active", user.is_active)
    ensure_not_last_active_admin(user, new_role, new_is_active)
    saved = serializer.save()
    if saved.role == User.Role.REGIONAL_MANAGER:
        assign_all_stores_to_regional_manager(saved)
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


def ensure_not_last_active_admin(
    user: User, new_role: str, new_is_active: bool
) -> None:
    """Refuse to remove the only active admin from the admin role."""
    if user.role != User.Role.ADMIN or not user.is_active:
        return
    keeps_admin = new_role == User.Role.ADMIN and new_is_active
    if keeps_admin:
        return
    others = (
        User.objects.filter(role=User.Role.ADMIN, is_active=True)
        .exclude(pk=user.pk)
        .count()
    )
    if others == 0:
        raise PermissionDenied(LAST_ADMIN_DENIED)
