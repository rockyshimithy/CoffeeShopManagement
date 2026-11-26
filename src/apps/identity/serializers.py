from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from core.fields import ObjectIdField

from .models import Employee, User
from .permissions import ROLE_DENIED, STORE_DENIED

READ_ONLY_PROFILE_FIELDS = ("role", "store_ids", "is_active")

ROLES_BY_ACTOR = {
    User.Role.ADMIN: set(User.Role.values),
    User.Role.REGIONAL_MANAGER: {User.Role.BARISTA, User.Role.SUPERVISOR},
    User.Role.MANAGER: {User.Role.BARISTA, User.Role.SUPERVISOR},
}

ACCOUNT_FIELDS = (
    "id",
    "email",
    "role",
    "store_ids",
    "is_active",
    "first_name",
    "last_name",
    "date_joined",
)

DUPLICATE_EMAIL = "An account with this email already exists."


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, write_only=True)

    def validate_email(self, value):
        return value.strip().lower()


def clean_email(value, instance=None):
    """Lowercase the address and refuse one already on another account."""
    email = value.strip().lower()
    taken = User.objects.filter(email=email)
    if instance is not None:
        taken = taken.exclude(pk=instance.pk)
    if taken.exists():
        raise serializers.ValidationError(DUPLICATE_EMAIL)
    return email


def save_account(instance, validated_data):
    """Apply the validated fields, hashing the password when one arrives."""
    password = validated_data.pop("password", None)
    for field, value in validated_data.items():
        setattr(instance, field, value)
    if password is not None:
        instance.set_password(password)
    instance.save()
    return instance


class AccountReadSerializer(serializers.ModelSerializer):
    id = ObjectIdField(read_only=True)
    store_ids = serializers.ListField(child=ObjectIdField(), read_only=True)

    class Meta:
        model = User
        fields = ACCOUNT_FIELDS
        read_only_fields = ("role", "is_active", "date_joined")


class AccountProfileSerializer(AccountReadSerializer):
    """The caller's own account. Only the personal fields are writable here."""

    password = serializers.CharField(
        write_only=True, required=False, trim_whitespace=False
    )

    class Meta(AccountReadSerializer.Meta):
        fields = (*ACCOUNT_FIELDS, "password")
        extra_kwargs = {"email": {"required": False}}

    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            for field in READ_ONLY_PROFILE_FIELDS:
                if field in data:
                    raise serializers.ValidationError(
                        {field: ["This field is read only."]}
                    )
        return super().to_internal_value(data)

    def validate_email(self, value):
        return clean_email(value, self.instance)

    def update(self, instance, validated_data):
        return save_account(instance, validated_data)


class AccountWriteSerializer(AccountReadSerializer):
    """A staff account created or changed by an admin, manager, or regional."""

    store_ids = serializers.ListField(
        child=ObjectIdField(), required=False, default=list
    )
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta(AccountReadSerializer.Meta):
        fields = (*ACCOUNT_FIELDS, "password")
        read_only_fields = ("date_joined",)
        # The case insensitive check lives in validate_email, so the case
        # sensitive one would only add a second, duplicate message.
        extra_kwargs = {"email": {"validators": []}}

    def validate_email(self, value):
        return clean_email(value, self.instance)

    def validate_password(self, value):
        user = self.instance or User(email=self.initial_data.get("email", ""))
        validate_password(value, user=user)
        return value

    def validate_role(self, value):
        actor = self.context.get("actor")
        allowed = ROLES_BY_ACTOR.get(actor.role) if actor is not None else None
        if allowed is not None and value not in allowed:
            raise PermissionDenied(ROLE_DENIED)
        return value

    def validate_store_ids(self, value):
        from apps.stores.models import Store

        known = set(Store.objects.filter(pk__in=value).values_list("pk", flat=True))
        missing = [str(store_id) for store_id in value if store_id not in known]
        if missing:
            raise serializers.ValidationError(f"No store exists with id {missing[0]}.")
        actor = self.context.get("actor")
        if actor is not None and actor.role == User.Role.MANAGER:
            outside = [
                store_id for store_id in value if store_id not in actor.store_ids
            ]
            if outside:
                raise PermissionDenied(STORE_DENIED)
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)

    def update(self, instance, validated_data):
        return save_account(instance, validated_data)


class EmployeeSerializer(serializers.ModelSerializer):
    id = ObjectIdField(read_only=True)
    user_id = ObjectIdField()
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_name = serializers.SerializerMethodField()
    hire_date = serializers.DateField()

    class Meta:
        model = Employee
        fields = ("id", "user_id", "user_email", "user_name", "hire_date")

    def get_user_name(self, employee):
        return f"{employee.user.first_name} {employee.user.last_name}".strip()

    def validate(self, attrs):
        if self.instance is not None and "user_id" in attrs:
            raise serializers.ValidationError(
                {"user_id": ["This field cannot be changed."]}
            )
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        actor = self.context.get("actor")
        if actor is not None and actor.role == User.Role.BARISTA:
            data.pop("user_email", None)
        return data
