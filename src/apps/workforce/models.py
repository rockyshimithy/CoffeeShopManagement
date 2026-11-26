from django.db import models
from django_mongodb_backend.fields import ObjectIdField


class Shift(models.Model):
    """One employee working in one store over one interval.

    Both references use string labels, so this context imports no other
    context's model. The cascades are what remove shifts when a store or an
    account is deleted (FR-024, FR-025).
    """

    employee = models.ForeignKey(
        "identity.Employee", on_delete=models.CASCADE, related_name="shifts"
    )
    store = models.ForeignKey(
        "stores.Store", on_delete=models.CASCADE, related_name="shifts"
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=["store", "starts_at"]),
            models.Index(fields=["employee", "starts_at"]),
        ]

    def __str__(self):
        return (
            f"{self.employee} in {self.store} from {self.starts_at} to {self.ends_at}"
        )


class ScheduleRevision(models.Model):
    """Per store counter with two jobs: the overlap write guard and the cache key.

    Every shift write bumps the row of each store the employee belongs to. Two
    concurrent writes for one employee therefore always share a document, which
    is what makes MongoDB abort one of them instead of letting both pass the
    overlap check. The same number is part of the schedule cache key, so a
    committed write makes every earlier cached page unreachable.
    """

    store_id = ObjectIdField(unique=True)
    revision = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.store_id}: {self.revision}"


class ScheduleSnapshot(models.Model):
    """One cached schedule page. Body holds the serialized page, links excluded."""

    key = models.CharField(max_length=64, unique=True)
    body = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.key
