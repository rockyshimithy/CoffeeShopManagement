
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.workforce.urls')),
    path('', include('apps.stores.urls')),
    path('', include('apps.catalog.urls')),
]
