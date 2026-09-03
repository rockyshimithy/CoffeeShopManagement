from django.urls import path
from . import views

app_name = 'workforce'

urlpatterns = [
    path('employees/', views.EmployeeList.as_view(), name=views.EmployeeList.name),
    path('employee/<int:pk>/', views.EmployeeDetail.as_view(), name=views.EmployeeDetail.name),
    
    path('', views.ApiRoot.as_view(), name=views.ApiRoot.name),
]
