import django_filters
from bson import ObjectId
from bson.errors import InvalidId

from .models import Employee, User


class UserFilter(django_filters.FilterSet):
    role = django_filters.ChoiceFilter(choices=User.Role.choices)
    is_active = django_filters.BooleanFilter()
    store = django_filters.CharFilter(method="filter_store")

    class Meta:
        model = User
        fields = []

    def filter_store(self, queryset, name, value):
        try:
            store_id = ObjectId(value)
        except (InvalidId, TypeError):
            return queryset.none()
        return queryset.filter(store_ids__contains=[store_id])


class EmployeeFilter(django_filters.FilterSet):
    store = django_filters.CharFilter(method="filter_store")

    class Meta:
        model = Employee
        fields = []

    def filter_store(self, queryset, name, value):
        try:
            store_id = ObjectId(value)
        except (InvalidId, TypeError):
            return queryset.none()
        return queryset.filter(user__store_ids__contains=[store_id])
