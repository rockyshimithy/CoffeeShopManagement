from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.identity.urls")),
    path("api/", include("apps.stores.urls")),
    path("api/", include("apps.catalog.urls")),
    path("api/", include("apps.workforce.urls")),
]
