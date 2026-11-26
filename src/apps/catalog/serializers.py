from rest_framework import serializers

from core.fields import ObjectIdField

from .models import Product


class ProductSerializer(serializers.ModelSerializer):
    id = ObjectIdField(read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "description",
            "price",
        )
