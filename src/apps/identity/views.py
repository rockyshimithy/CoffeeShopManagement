from django.contrib.auth import authenticate, login, logout
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.shortcuts import object_id_or_404

from .filters import EmployeeFilter, UserFilter
from .models import Employee, User
from .permissions import (
    ROLE_DENIED,
    can,
    require_account_access,
    require_user_read,
)
from .serializers import (
    AccountProfileSerializer,
    AccountReadSerializer,
    AccountWriteSerializer,
    EmployeeSerializer,
    LoginSerializer,
)
from .services import (
    create_account,
    create_employee,
    delete_account,
    update_account,
    update_employee,
    visible_accounts,
    visible_employees,
)

INVALID_CREDENTIALS = "Invalid email or password."


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response(
                {"detail": INVALID_CREDENTIALS}, status=status.HTTP_401_UNAUTHORIZED
            )
        login(request, user)
        return Response(AccountProfileSerializer(request.user).data)


class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = AccountProfileSerializer

    def get_object(self):
        return self.request.user


class AccountAccessMixin:
    """Only admins, regional managers, and managers reach the accounts API."""

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not can(request.user, "account.read"):
            raise PermissionDenied(ROLE_DENIED)


class AccountListCreateView(AccountAccessMixin, generics.ListCreateAPIView):
    filter_backends = (DjangoFilterBackend,)
    filterset_class = UserFilter

    def get_queryset(self):
        return visible_accounts(self.request.user).order_by("email")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return AccountWriteSerializer
        return AccountReadSerializer

    def create(self, request, *args, **kwargs):
        user = create_account(request.user, request.data)
        return Response(
            AccountReadSerializer(user).data, status=status.HTTP_201_CREATED
        )


class AccountDetailView(AccountAccessMixin, generics.GenericAPIView):
    def get_object(self):
        target = object_id_or_404(User, self.kwargs["pk"])
        require_account_access(self.request.user, target)
        return target

    def get(self, request, *args, **kwargs):
        return Response(AccountReadSerializer(self.get_object()).data)

    def patch(self, request, *args, **kwargs):
        target = self.get_object()
        user = update_account(request.user, target, request.data)
        return Response(AccountReadSerializer(user).data)

    def delete(self, request, *args, **kwargs):
        delete_account(request.user, self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)


class ActorContextMixin:
    """Give the serializer the actor, so it can shape the response by role."""

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["actor"] = self.request.user
        return context


class EmployeeListCreateView(ActorContextMixin, generics.ListCreateAPIView):
    serializer_class = EmployeeSerializer
    filter_backends = (DjangoFilterBackend,)
    filterset_class = EmployeeFilter

    def get_queryset(self):
        return visible_employees(self.request.user).order_by("-hire_date")

    def create(self, request, *args, **kwargs):
        employee = create_employee(request.user, request.data)
        return Response(
            self.get_serializer(employee).data, status=status.HTTP_201_CREATED
        )


class EmployeeDetailView(ActorContextMixin, generics.GenericAPIView):
    serializer_class = EmployeeSerializer

    def get_object(self):
        employee = object_id_or_404(Employee, self.kwargs["pk"])
        require_user_read(self.request.user, employee.user)
        return employee

    def get(self, request, *args, **kwargs):
        return Response(self.get_serializer(self.get_object()).data)

    def patch(self, request, *args, **kwargs):
        employee = self.get_object()
        updated = update_employee(request.user, employee, request.data)
        return Response(self.get_serializer(updated).data)
