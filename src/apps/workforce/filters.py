import django_filters
from .models import Employee


class EmployeeFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(name='name', lookup_expr='icontains')
    last_name = django_filters.CharFilter(name='last_name', lookup_expr='icontains')
    email = django_filters.CharFilter(name="email", lookup_expr='icontains')
    position = django_filters.CharFilter(name='position', lookup_expr='iexact')

    class Meta:
        model = Employee
        fields = ['name', 'last_name', 'email', 'position']
