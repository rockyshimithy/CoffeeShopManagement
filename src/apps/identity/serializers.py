from rest_framework import serializers

from core.fields import ObjectIdField

from .models import User

READ_ONLY_PROFILE_FIELDS = ("role", "store_ids", "is_active")


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, write_only=True)

    def validate_email(self, value):
        return value.strip().lower()


class AccountProfileSerializer(serializers.ModelSerializer):
    id = ObjectIdField(read_only=True)
    store_ids = serializers.ListField(child=ObjectIdField(), read_only=True)
    password = serializers.CharField(
        write_only=True, required=False, trim_whitespace=False
    )

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "role",
            "store_ids",
            "is_active",
            "first_name",
            "last_name",
            "date_joined",
            "password",
        )
        read_only_fields = (*READ_ONLY_PROFILE_FIELDS, "date_joined")
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
        return value.strip().lower()

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password is not None:
            instance.set_password(password)
        instance.save()
        return instance
