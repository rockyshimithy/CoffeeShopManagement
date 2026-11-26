from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics

from apps.identity.permissions import require_action
from core.shortcuts import object_id_or_404

from .filters import ProductFilter
from .models import Product
from .serializers import ProductSerializer


class ProductList(generics.ListCreateAPIView):
    """Catalog reads are global (001 FR-022), so no store filter applies here.

    Writing the catalog is a role decision, and it is made in the permission
    helper rather than in this view.
    """

    queryset = Product.objects.order_by("name")
    serializer_class = ProductSerializer
    filter_backends = (DjangoFilterBackend,)
    filterset_class = ProductFilter
    name = "product-list"

    def create(self, request, *args, **kwargs):
        require_action(request.user, "product.change")
        return super().create(request, *args, **kwargs)


class ProductDetail(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProductSerializer
    name = "product-detail"

    def get_object(self):
        """Load by ObjectId. The generic path cannot do it, see research R11."""
        return object_id_or_404(Product, self.kwargs["pk"])

    def update(self, request, *args, **kwargs):
        require_action(request.user, "product.change")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        require_action(request.user, "product.change")
        return super().destroy(request, *args, **kwargs)


class ApiRoot(generics.GenericAPIView):
    name = "api-root"
