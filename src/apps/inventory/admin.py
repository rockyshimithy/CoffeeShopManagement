from django.contrib import admin

from .models import Stock, StockEvent


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    """Read only. FR-027 makes the admin something other than a write path.

    Every legal change goes through the single service function, which owns the
    transaction and the event insert. A ModelAdmin that could save would let the
    number and the events disagree.
    """

    list_display = ("product", "pool_type", "store", "current_stock", "last_count")

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StockEvent)
class StockEventAdmin(admin.ModelAdmin):
    """Read only, append only. An event is never edited or deleted (FR-029)."""

    list_display = ("kind", "type", "product_id", "pool_type", "at", "by_name")

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
