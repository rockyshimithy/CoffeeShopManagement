from rest_framework.exceptions import PermissionDenied

from .models import User

STORE_DENIED = "This record is outside your store access."
ROLE_DENIED = "Your role may not perform this action."

ACTIONS = frozenset(
    {
        "store.create",
        "store.change",
        "store.delete",
        "account.create",
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


def can(actor, action, store_id=None):
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


def scope_stores(queryset, actor, field="store_id"):
    """Limit a queryset to the actor's store assignments.

    ``field`` is the name of the store reference on the queryset's model, so a
    ``Shift`` uses the default ``store_id`` and a ``Store`` list passes
    ``field="pk"``. When the field holds an array, as on ``User.store_ids``,
    MongoDB ``$in`` already matches documents with any of the given ids, so
    overlap and scalar scoping share one code path.
    """
    if actor.role == User.Role.ADMIN:
        return queryset
    return queryset.filter(**{f"{field}__in": actor.store_ids})


def require_store_access(actor, store_id):
    if actor.role == User.Role.ADMIN:
        return
    if store_id is None or store_id not in actor.store_ids:
        raise PermissionDenied(STORE_DENIED)


def require_action(actor, action, store_id=None):
    if not can(actor, action):
        raise PermissionDenied(ROLE_DENIED)
    if store_id is not None:
        require_store_access(actor, store_id)
