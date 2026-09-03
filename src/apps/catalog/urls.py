from django.urls import path
from . import views

app_name = 'catalog'

urlpatterns = [
    path('products/', views.ProductList.as_view(), name=views.ProductList.name),
    path('products/<int:pk>/', views.ProductDetail.as_view(), name=views.ProductDetail.name),

    path('', views.ApiRoot.as_view(), name=views.ApiRoot.name),
]
