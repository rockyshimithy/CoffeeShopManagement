from bson import ObjectId
from django.db.models import QuerySet
from django_mongodb_backend.transaction import atomic
from rest_framework.exceptions import PermissionDenied

from apps.identity.models import User
from apps.identity.permissions import ROLE_DENIED, can
from apps.identity.services import (
    add_store_to_regional_managers,
    remove_store_from_all_users,
)
from core.transactions import retry_on_conflict

from .models import Store
from .serializers import StoreSerializer


def all_store_ids() -> QuerySet:
    """Public read for other contexts. Returns ids, never Store instances."""
    return Store.objects.values_list("pk", flat=True)


def store_exists(store_id: ObjectId) -> bool:
    """Public read for other contexts: does this store exist?"""
    return Store.objects.filter(pk=store_id).exists()


def create_store(actor: User, data: dict) -> Store:
    """Create a store and give it to every regional manager.

    The insert and the assignment updates touch two collections, so one
    transaction covers both. A conflicting write aborts that transaction with a
    ``DatabaseError``, and the whole operation is retried from the start.
    """
    if not can(actor, "store.create"):
        raise PermissionDenied(ROLE_DENIED)
    serializer = StoreSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    fields = dict(serializer.validated_data)

    def operation():
        with atomic():
            store = Store.objects.create(**fields)
            add_store_to_regional_managers(store.pk)
            if actor.role == User.Role.REGIONAL_MANAGER:
                _ensure_assigned(actor.pk, store.pk)
            return store

    return retry_on_conflict(operation)


def delete_store(actor: User, store: Store) -> None:
    """Delete a store and remove its id from every account."""
    if not can(actor, "store.delete"):
        raise PermissionDenied(ROLE_DENIED)
    store_id = store.pk

    def operation():
        with atomic():
            Store.objects.filter(pk=store_id).delete()
            remove_store_from_all_users(store_id)

    return retry_on_conflict(operation)


def _ensure_assigned(user_id: ObjectId, store_id: ObjectId) -> None:
    """Append the store to one account, reading the list inside the transaction."""
    user = User.objects.get(pk=user_id)
    if store_id not in user.store_ids:
        User.objects.filter(pk=user_id).update(store_ids=[*user.store_ids, store_id])
