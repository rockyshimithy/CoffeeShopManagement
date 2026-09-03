from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.reverse import reverse


from .filters import ProductFilter
from .models import Product
from .serializers import ProductSerializer


class ProductList(generics.ListCreateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filter_backends = (DjangoFilterBackend,)
    filter_class = ProductFilter
    name = 'product-list'


class ProductDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    name = 'product-detail'


class ApiRoot(generics.GenericAPIView):
    name = 'api-root'

    # def get(self, request, *args, **kwargs):
    #     return Response({
    #         'feiras': reverse(FeiraList.name, request=request)
    #     })
