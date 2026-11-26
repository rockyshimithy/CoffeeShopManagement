from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.identity.permissions import (
    ROLE_DENIED,
    can,
    require_store_access,
    scope_stores,
)
from core.shortcuts import object_id_or_404

from .filters import StoreFilter
from .models import Store
from .serializers import StoreSerializer
from .services import create_store, delete_store


class StoreList(generics.ListCreateAPIView):
    serializer_class = StoreSerializer
    filter_backends = (DjangoFilterBackend,)
    filterset_class = StoreFilter

    def get_queryset(self):
        scoped = scope_stores(Store.objects.all(), self.request.user, field="pk")
        return scoped.order_by("name")

    def create(self, request, *args, **kwargs):
        store = create_store(request.user, request.data)
        return Response(StoreSerializer(store).data, status=status.HTTP_201_CREATED)


class StoreDetail(generics.GenericAPIView):
    serializer_class = StoreSerializer

    def get_object(self):
        store = object_id_or_404(Store, self.kwargs["pk"])
        require_store_access(self.request.user, store.pk)
        return store

    def get(self, request, *args, **kwargs):
        return Response(StoreSerializer(self.get_object()).data)

    def patch(self, request, *args, **kwargs):
        if not can(request.user, "store.change"):
            raise PermissionDenied(ROLE_DENIED)
        store = self.get_object()
        serializer = StoreSerializer(store, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, *args, **kwargs):
        store = self.get_object()
        delete_store(request.user, store)
        return Response(status=status.HTTP_204_NO_CONTENT)
