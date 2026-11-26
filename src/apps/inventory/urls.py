from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("stock/", views.StockList.as_view(), name=views.StockList.name),
    path("stock/low/", views.StockLow.as_view(), name=views.StockLow.name),
    path(
        "stock/movements/",
        views.MovementList.as_view(),
        name=views.MovementList.name,
    ),
    path("stock/counts/", views.CountList.as_view(), name=views.CountList.name),
    path(
        "stock/<str:pk>/events/",
        views.StockEventList.as_view(),
        name=views.StockEventList.name,
    ),
]
