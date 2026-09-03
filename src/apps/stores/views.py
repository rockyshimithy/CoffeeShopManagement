from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.reverse import reverse


from .filters import StoreFilter
from .models import Store
from .serializers import StoreSerializer


class StoreList(generics.ListCreateAPIView):
    queryset = Store.objects.all()
    serializer_class = StoreSerializer
    filter_backends = (DjangoFilterBackend,)
    filter_class = StoreFilter
    name = 'store-list'


class StoreDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Store.objects.all()
    serializer_class = StoreSerializer
    name = 'store-detail'


class ApiRoot(generics.GenericAPIView):
    name = 'api-root'

    # def get(self, request, *args, **kwargs):
    #     return Response({
    #         'feiras': reverse(FeiraList.name, request=request)
    #     })
