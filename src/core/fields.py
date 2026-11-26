from bson import ObjectId, errors
from rest_framework import serializers


class ObjectIdField(serializers.CharField):
    """An ObjectId that travels as a 24 character hex string."""

    default_error_messages = {"invalid": "Enter a valid ObjectId."}

    def to_representation(self, value):
        return str(value)

    def to_internal_value(self, data):
        try:
            return ObjectId(data)
        except (errors.InvalidId, TypeError):
            self.fail("invalid")
