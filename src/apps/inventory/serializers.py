from rest_framework import serializers

from core.fields import ObjectIdField, QuantityField

from .models import Pool, Stock, StockEvent


class StockSerializer(serializers.ModelSerializer):
    """The read shape of one pool's number.

    ``product_name``, ``unit``, ``store_name``, and the threshold arrive in the
    serializer context, batched once per page after pagination.
    """

    id = ObjectIdField(read_only=True)
    product_id = ObjectIdField(read_only=True)
    product_name = serializers.SerializerMethodField()
    unit = serializers.SerializerMethodField()
    pool = serializers.CharField(source="pool_type", read_only=True)
    store_id = ObjectIdField(read_only=True)
    store_name = serializers.SerializerMethodField()
    current_stock = QuantityField(read_only=True)
    last_count = QuantityField(read_only=True)
    is_low = serializers.SerializerMethodField()

    class Meta:
        model = Stock
        fields = (
            "id",
            "product_id",
            "product_name",
            "unit",
            "pool",
            "store_id",
            "store_name",
            "current_stock",
            "last_count",
            "last_event_at",
            "is_low",
        )

    def _label(self, row) -> tuple:
        return self.context.get("labels", {}).get(str(row.product_id), ("", ""))

    def get_product_name(self, row) -> str:
        return self._label(row)[0]

    def get_unit(self, row) -> str:
        return self._label(row)[1]

    def get_store_name(self, row):
        if row.store_id is None:
            return None
        return self.context.get("store_names", {}).get(str(row.store_id))

    def get_is_low(self, row) -> bool:
        threshold = self.context.get("thresholds", {}).get(str(row.product_id))
        if threshold is None:
            return False
        return row.current_stock < threshold


class StockEventSerializer(serializers.ModelSerializer):
    """The read shape of one recorded change. Append only."""

    id = ObjectIdField(read_only=True)
    stock_id = ObjectIdField(read_only=True)
    product_id = ObjectIdField(read_only=True)
    store_id = ObjectIdField(read_only=True)
    by_id = ObjectIdField(read_only=True)
    pool = serializers.CharField(source="pool_type", read_only=True)
    quantity = QuantityField(read_only=True)
    counted = QuantityField(read_only=True)

    class Meta:
        model = StockEvent
        fields = (
            "id",
            "stock_id",
            "product_id",
            "pool",
            "store_id",
            "kind",
            "type",
            "quantity",
            "counted",
            "by_id",
            "by_name",
            "at",
            "note",
        )


class EventReadSerializer(StockEventSerializer):
    """One recorded change with the names the report and the feed show."""

    product_name = serializers.SerializerMethodField()
    unit = serializers.SerializerMethodField()
    store_name = serializers.SerializerMethodField()

    class Meta(StockEventSerializer.Meta):
        fields = StockEventSerializer.Meta.fields + (
            "product_name",
            "unit",
            "store_name",
        )

    def _label(self, row) -> tuple:
        return self.context.get("labels", {}).get(str(row.product_id), ("", ""))

    def get_product_name(self, row) -> str:
        return self._label(row)[0]

    def get_unit(self, row) -> str:
        return self._label(row)[1]

    def get_store_name(self, row):
        if row.store_id is None:
            return None
        return self.context.get("store_names", {}).get(str(row.store_id))


class WasteTotalSerializer(serializers.Serializer):
    """One item's waste in the window, with its exact total."""

    product_id = ObjectIdField(read_only=True)
    product_name = serializers.SerializerMethodField()
    unit = serializers.SerializerMethodField()
    total = QuantityField(read_only=True)
    events = serializers.IntegerField(read_only=True)

    def _label(self, row) -> tuple:
        return self.context.get("labels", {}).get(str(row["product_id"]), ("", ""))

    def get_product_name(self, row) -> str:
        return self._label(row)[0]

    def get_unit(self, row) -> str:
        return self._label(row)[1]


class WasteReportQuerySerializer(serializers.Serializer):
    """The window the waste report reads, and the two optional narrowings."""

    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    store = ObjectIdField(required=False)
    product = ObjectIdField(required=False)

    def validate(self, data):
        if data["start"] > data["end"]:
            raise serializers.ValidationError(
                {"end": ["The end must not be earlier than the start."]}
            )
        return data


class MovementWriteSerializer(serializers.Serializer):
    """The create shape for a delivery, a sale, or waste.

    Field names on the wire are ``product``, ``pool``, and ``store``; the service
    wants ids, so ``validate`` renames them once and nowhere else.
    """

    product = ObjectIdField()
    pool = serializers.ChoiceField(choices=Pool.choices)
    store = ObjectIdField(required=False, allow_null=True)
    type = serializers.ChoiceField(choices=["RECEIVED", "SOLD", "WASTE"])
    quantity = QuantityField()
    note = serializers.CharField(required=False, allow_blank=True, default="")
    at = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, attrs):
        return {
            "product_id": attrs["product"],
            "pool_type": attrs["pool"],
            "store_id": attrs.get("store"),
            "movement_type": attrs["type"],
            "quantity": attrs["quantity"],
            "note": attrs.get("note") or "",
            "at": attrs.get("at"),
        }


class CountWriteSerializer(serializers.Serializer):
    """The count shape. A count has no direction, so type and quantity are refused."""

    product = ObjectIdField()
    pool = serializers.ChoiceField(choices=Pool.choices)
    store = ObjectIdField(required=False, allow_null=True)
    counted = QuantityField()
    note = serializers.CharField(required=False, allow_blank=True, default="")
    at = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, attrs):
        errors = {
            name: ["A count has no direction."]
            for name in ("type", "quantity")
            if name in self.initial_data
        }
        if errors:
            raise serializers.ValidationError(errors)
        return {
            "product_id": attrs["product"],
            "pool_type": attrs["pool"],
            "store_id": attrs.get("store"),
            "counted": attrs["counted"],
            "note": attrs.get("note") or "",
            "at": attrs.get("at"),
        }
