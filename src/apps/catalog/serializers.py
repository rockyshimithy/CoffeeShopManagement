from rest_framework import serializers

from core.fields import ObjectIdField, QuantityField

from .models import Product


class ProductSerializer(serializers.ModelSerializer):
    id = ObjectIdField(read_only=True)
    low_stock_threshold = QuantityField(required=False, allow_null=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "description",
            "price",
            "unit",
            "low_stock_threshold",
        )
