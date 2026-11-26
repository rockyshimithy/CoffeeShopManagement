import django_filters

from .models import Store


class StoreFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(field_name="name", lookup_expr="icontains")
    address = django_filters.CharFilter(field_name="address", lookup_expr="icontains")
    postal_code = django_filters.CharFilter(
        field_name="postal_code", lookup_expr="iexact"
    )

    class Meta:
        model = Store
        fields = ["name", "address", "postal_code"]
