from rest_framework import serializers

from core.fields import ObjectIdField

from .models import Store


class StoreSerializer(serializers.ModelSerializer):
    id = ObjectIdField(read_only=True)

    class Meta:
        model = Store
        fields = ("id", "name", "address", "postal_code")
        extra_kwargs = {"name": {"required": True, "allow_blank": False}}
