from django.urls import path

from . import views

app_name = "stores"

urlpatterns = [
    path("stores/", views.StoreList.as_view(), name="store-list"),
    path("stores/<str:pk>/", views.StoreDetail.as_view(), name="store-detail"),
]
