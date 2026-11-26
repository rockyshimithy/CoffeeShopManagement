from django.db import models
from django_mongodb_backend.fields import ObjectIdField


class Pool(models.TextChoices):
    BRANCH = "BRANCH", "Branch"
    ONLINE = "ONLINE", "Online"


class Movement(models.TextChoices):
    RECEIVED = "RECEIVED", "Received"
    SOLD = "SOLD", "Sold"
    WASTE = "WASTE", "Waste"


class EventKind(models.TextChoices):
    MOVEMENT = "MOVEMENT", "Movement"
    COUNT = "COUNT", "Count"


class Stock(models.Model):
    """How much of one product sits in one pool.

    A row is one pool: ``BRANCH`` carries a store and ``ONLINE`` carries none, so
    two pools can never share a number and no transfer operation can exist. The
    unique index is what stops two concurrent first deliveries from creating two
    rows for the same pool.

    No field here is ever written from a value read earlier. The number moves by
    a targeted update, which is invariant I4.
    """

    product = models.ForeignKey(
        "catalog.Product", on_delete=models.CASCADE, related_name="stock_rows"
    )
    pool_type = models.CharField(max_length=8, choices=Pool.choices)
    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="stock_rows",
    )
    current_stock = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    last_count = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    last_count_at = models.DateTimeField(null=True, blank=True)
    last_event_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product", "pool_type", "store"], name="uniq_stock_per_pool"
            )
        ]
        indexes = [
            models.Index(fields=["product", "pool_type", "store"]),
            models.Index(fields=["store", "pool_type"]),
        ]

    def __str__(self):
        return f"{self.product_id} in {self.pool_type}: {self.current_stock}"


class StockEvent(models.Model):
    """One change to one stock row. Append only, never modified.

    The actor is stored as an id and a name snapshot rather than a foreign key.
    A cascade would delete an account's history and break the derivable
    discrepancy, and a ``SET_NULL`` would rewrite stored events, which FR-029
    forbids.

    ``product_id`` and ``store_id`` are copies rather than relations, because
    M3 reads events across products and cannot afford a join for each one.
    """

    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name="events")
    product_id = ObjectIdField()
    pool_type = models.CharField(max_length=8, choices=Pool.choices)
    store_id = ObjectIdField(null=True, blank=True)
    kind = models.CharField(max_length=8, choices=EventKind.choices)
    type = models.CharField(
        max_length=8, choices=Movement.choices, null=True, blank=True
    )
    quantity = models.DecimalField(
        max_digits=12, decimal_places=3, null=True, blank=True
    )
    counted = models.DecimalField(
        max_digits=12, decimal_places=3, null=True, blank=True
    )
    by_id = ObjectIdField()
    by_name = models.CharField(max_length=120)
    at = models.DateTimeField()
    note = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["stock", "at"]),
            models.Index(fields=["product_id", "at"]),
            models.Index(fields=["store_id", "at"]),
        ]

    def __str__(self):
        return f"{self.kind} {self.quantity or self.counted} at {self.at}"
