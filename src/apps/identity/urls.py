from django.urls import path

from . import views

app_name = "identity"

urlpatterns = [
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("auth/me/", views.MeView.as_view(), name="me"),
    path("accounts/", views.AccountListCreateView.as_view(), name="account-list"),
    path(
        "accounts/<str:pk>/",
        views.AccountDetailView.as_view(),
        name="account-detail",
    ),
    path(
        "employees/",
        views.EmployeeListCreateView.as_view(),
        name="employee-list",
    ),
    path(
        "employees/<str:pk>/",
        views.EmployeeDetailView.as_view(),
        name="employee-detail",
    ),
]
