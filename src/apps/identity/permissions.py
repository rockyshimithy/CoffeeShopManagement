from bson import ObjectId
from django.db.models import QuerySet
from rest_framework.exceptions import PermissionDenied

from .models import User

STORE_DENIED = "This record is outside your store access."
ROLE_DENIED = "Your role may not perform this action."
LAST_ADMIN_DENIED = "The last active admin cannot be deactivated or demoted."

ACTIONS = frozenset(
    {
        "store.create",
        "store.change",
        "store.delete",
        "account.create",
        "account.read",
        "account.change",
        "account.deactivate",
        "employee.read",
        "employee.create",
        "employee.change",
        "shift.schedule",
    }
)

ROLE_ACTIONS = {
    "store.create": {User.Role.ADMIN, User.Role.REGIONAL_MANAGER},
    "store.change": {User.Role.ADMIN, User.Role.REGIONAL_MANAGER},
    "store.delete": {User.Role.ADMIN},
    "account.create": {
        User.Role.ADMIN,
        User.Role.REGIONAL_MANAGER,
        User.Role.MANAGER,
    },
    "account.read": {
        User.Role.ADMIN,
        User.Role.REGIONAL_MANAGER,
        User.Role.MANAGER,
    },
    "account.change": {
        User.Role.ADMIN,
        User.Role.REGIONAL_MANAGER,
        User.Role.MANAGER,
    },
    "account.deactivate": {
        User.Role.ADMIN,
        User.Role.REGIONAL_MANAGER,
        User.Role.MANAGER,
    },
    "employee.read": {
        User.Role.ADMIN,
        User.Role.REGIONAL_MANAGER,
        User.Role.MANAGER,
        User.Role.SUPERVISOR,
        User.Role.BARISTA,
    },
    "employee.create": {
        User.Role.ADMIN,
        User.Role.REGIONAL_MANAGER,
        User.Role.MANAGER,
    },
    "employee.change": {
        User.Role.ADMIN,
        User.Role.REGIONAL_MANAGER,
        User.Role.MANAGER,
    },
    "shift.schedule": {
        User.Role.ADMIN,
        User.Role.REGIONAL_MANAGER,
        User.Role.MANAGER,
        User.Role.SUPERVISOR,
    },
}


def can(actor: User | None, action: str, store_id: ObjectId | None = None) -> bool:
    """Return True when the actor may perform the action, optionally in one store.

    The role decides the action, the store assignment decides the scope, and
    ADMIN is the only role that skips the store check.
    """
    if actor is None or not actor.is_active:
        return False
    allowed = ROLE_ACTIONS.get(action)
    if allowed is None or actor.role not in allowed:
        return False
    if store_id is None or actor.role == User.Role.ADMIN:
        return True
    return store_id in actor.store_ids


def scope_stores(
    queryset: QuerySet,
    actor: User,
    field: str = "store_id",
    overlap: bool = False,
) -> QuerySet:
    """Limit a queryset to the actor's store assignments.

    ``field`` is the name of a store reference on the queryset's model, so a
    ``Shift`` uses the default ``store_id`` and a ``Store`` list passes
    ``field="pk"``. A scalar reference uses ``in``; an array reference such as
    ``User.store_ids`` must pass ``overlap=True``, because ``in`` on an array
    field compares whole arrays instead of matching one element.
    """
    if actor.role == User.Role.ADMIN:
        return queryset
    lookup = "overlap" if overlap else "in"
    return queryset.filter(**{f"{field}__{lookup}": actor.store_ids})


def require_store_access(actor: User, store_id: ObjectId | None) -> None:
    if actor.role == User.Role.ADMIN:
        return
    if store_id is None or store_id not in actor.store_ids:
        raise PermissionDenied(STORE_DENIED)


def require_action(actor: User, action: str, store_id: ObjectId | None = None) -> None:
    if not can(actor, action):
        raise PermissionDenied(ROLE_DENIED)
    if store_id is not None:
        require_store_access(actor, store_id)


ACCOUNT_MANAGED_ROLES = frozenset({User.Role.BARISTA, User.Role.SUPERVISOR})


def shares_a_store(actor: User, target: User) -> bool:
    return bool(set(actor.store_ids) & set(target.store_ids))


def require_account_access(actor: User, target: User) -> None:
    """Read access to one account: admins and regionals see all, a manager
    sees own store staff and self."""
    if actor.role in (User.Role.ADMIN, User.Role.REGIONAL_MANAGER):
        return
    if actor.pk == target.pk:
        return
    if actor.role != User.Role.MANAGER:
        raise PermissionDenied(ROLE_DENIED)
    if target.role not in ACCOUNT_MANAGED_ROLES or not shares_a_store(actor, target):
        raise PermissionDenied(STORE_DENIED)


def require_account_change(actor: User, target: User) -> None:
    """Change access: an admin anywhere, a manager only own store staff, a
    regional manager only BARISTA and SUPERVISOR accounts."""
    if actor.role == User.Role.ADMIN or actor.pk == target.pk:
        return
    if actor.role not in (User.Role.MANAGER, User.Role.REGIONAL_MANAGER):
        raise PermissionDenied(ROLE_DENIED)
    if target.role not in ACCOUNT_MANAGED_ROLES:
        raise PermissionDenied(ROLE_DENIED)
    if actor.role == User.Role.MANAGER and not shares_a_store(actor, target):
        raise PermissionDenied(STORE_DENIED)


def require_user_read(actor: User, user: User) -> None:
    """Read an account or its profile: admin and regional see all, everyone
    else only a user who shares one of their stores."""
    if actor.role in (User.Role.ADMIN, User.Role.REGIONAL_MANAGER):
        return
    if not shares_a_store(actor, user):
        raise PermissionDenied(STORE_DENIED)


def require_user_in_scope(actor: User, user: User) -> None:
    """Write an employee profile: admin and regional reach any account, a
    manager only one in an own store, and no lower role at all."""
    if actor.role not in (
        User.Role.ADMIN,
        User.Role.REGIONAL_MANAGER,
        User.Role.MANAGER,
    ):
        raise PermissionDenied(ROLE_DENIED)
    require_user_read(actor, user)
