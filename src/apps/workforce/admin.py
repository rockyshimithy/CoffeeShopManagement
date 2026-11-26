from django.contrib import admin

from .models import Shift


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    """Read only. Every legal write goes through the shift service, which owns
    the overlap check and the revision bump, so the admin must not offer one."""

    list_display = ("employee", "store", "starts_at", "ends_at")

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
