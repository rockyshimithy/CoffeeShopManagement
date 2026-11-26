from django.urls import path

from . import views

app_name = "workforce"

urlpatterns = [
    path("shifts/", views.ShiftList.as_view(), name="shift-list"),
    path("shifts/<str:pk>/", views.ShiftDetail.as_view(), name="shift-detail"),
]
