import django_filters
from .models import Product


class ProductFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(name='name',
                                         lookup_expr='icontains')
    description = django_filters.CharFilter(name="description",
                                        lookup_expr='icontains')
    price = django_filters.CharFilter(name='price',
                                           lookup_expr='iexact')

    class Meta:
        model = Product
        fields = ['name', 'description', 'price']


