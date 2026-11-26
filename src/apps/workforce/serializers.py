from rest_framework import serializers

from core.fields import ObjectIdField

from .models import Shift


class ShiftSerializer(serializers.ModelSerializer):
    """The read shape: who, where, when, with both display names resolved."""

    id = ObjectIdField(read_only=True)
    employee_id = ObjectIdField(read_only=True)
    store_id = ObjectIdField(read_only=True)
    employee_name = serializers.SerializerMethodField()
    store_name = serializers.CharField(source="store.name", read_only=True)

    class Meta:
        model = Shift
        fields = (
            "id",
            "employee_id",
            "employee_name",
            "store_id",
            "store_name",
            "starts_at",
            "ends_at",
        )

    def get_employee_name(self, shift: Shift) -> str:
        user = shift.employee.user
        name = f"{user.first_name} {user.last_name}".strip()
        return name or user.email


class ShiftWriteSerializer(serializers.Serializer):
    """The create shape. Edits accept only the two instants (FR-010)."""

    employee_id = ObjectIdField()
    store_id = ObjectIdField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
