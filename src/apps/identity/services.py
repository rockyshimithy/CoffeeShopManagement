from rest_framework.exceptions import PermissionDenied

from .models import User

LAST_ADMIN = "The last active admin cannot be deactivated or demoted."


def _update_store_ids(user_id, store_ids):
    User.objects.filter(pk=user_id).update(store_ids=store_ids)


def add_store_to_regional_managers(store_id):
    """Append a new store to every regional manager.

    The id is always new when this runs, so the per document read and targeted
    update cannot drop a concurrent append of a different store. Both sit in
    the caller's transaction, and MongoDB aborts on a write conflict rather
    than losing one.
    """
    rows = User.objects.filter(role=User.Role.REGIONAL_MANAGER).values_list(
        "pk", "store_ids"
    )
    for user_id, store_ids in rows:
        if store_id not in store_ids:
            _update_store_ids(user_id, [*store_ids, store_id])


def remove_store_from_all_users(store_id):
    rows = User.objects.filter(store_ids__contains=[store_id]).values_list(
        "pk", "store_ids"
    )
    for user_id, store_ids in rows:
        remaining = [known for known in store_ids if known != store_id]
        if len(remaining) != len(store_ids):
            _update_store_ids(user_id, remaining)


def assign_all_stores_to_regional_manager(user):
    from apps.stores.services import all_store_ids

    _update_store_ids(user.pk, list(all_store_ids()))


def ensure_not_last_active_admin(user, new_role, new_is_active):
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
        raise PermissionDenied(LAST_ADMIN)
