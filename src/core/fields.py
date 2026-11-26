from decimal import Decimal

from bson import ObjectId, errors
from rest_framework import serializers


class ObjectIdField(serializers.CharField):
    """An ObjectId that travels as a 24 character hex string."""

    default_error_messages = {"invalid": "Enter a valid ObjectId."}

    def to_representation(self, value):
        if value is None:
            return None
        return str(value)

    def to_internal_value(self, data):
        try:
            return ObjectId(data)
        except (errors.InvalidId, TypeError):
            self.fail("invalid")


class QuantityField(serializers.DecimalField):
    """A quantity as an exact decimal string with no trailing zeros.

    Stock numbers are stored as ``Decimal128``, so they render as text and never
    as a float. ``1.500`` reads as ``1.5`` and ``2.000`` reads as ``2``, which is
    what a person expects from a litre count.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", 12)
        kwargs.setdefault("decimal_places", 3)
        kwargs.setdefault("coerce_to_string", False)
        super().__init__(**kwargs)

    def to_representation(self, value):
        if value is None:
            return None
        return format(Decimal(value).normalize(), "f")
