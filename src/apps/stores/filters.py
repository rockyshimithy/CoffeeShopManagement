import django_filters
from .models import Store


class StoreFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(name='name',
                                         lookup_expr='icontains')
    address = django_filters.CharFilter(name="address",
                                        lookup_expr='icontains')
    postal_code = django_filters.CharFilter(name='postal_code',
                                           lookup_expr='iexact')
    # manager = django_filters.CharFilter(name='manager', lookup_expr='iexact')

    class Meta:
        model = Store
        fields = ['name', 'address', 'postal_code']


