from django.urls import path
from . import views

app_name = 'stores'

urlpatterns = [
    path('stores/', views.StoreList.as_view(), name=views.StoreList.name),
    path('stores/<int:pk>/', views.StoreDetail.as_view(), name=views.StoreDetail.name),

    path('', views.ApiRoot.as_view(), name=views.ApiRoot.name),
]
