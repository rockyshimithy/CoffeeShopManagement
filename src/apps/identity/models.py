from django.contrib.auth.models import AbstractUser
from django.db import models
from django_mongodb_backend.fields import ArrayField, ObjectIdField

from .managers import UserManager


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        REGIONAL_MANAGER = "REGIONAL_MANAGER", "Regional manager"
        MANAGER = "MANAGER", "Manager"
        SUPERVISOR = "SUPERVISOR", "Supervisor"
        BARISTA = "BARISTA", "Barista"

    username = None
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=32, choices=Role.choices)
    store_ids = ArrayField(ObjectIdField(), default=list)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        indexes = [
            models.Index(fields=["store_ids"]),
            models.Index(fields=["role", "is_active"]),
        ]

    def __str__(self):
        return self.email


class Employee(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="employee")
    hire_date = models.DateField()

    def __str__(self):
        return f"{self.user} ({self.hire_date})"


class AdminGuard(models.Model):
    """One row that serializes every change which can remove an active admin.

    The last-admin rule reads a count and then writes. Under snapshot isolation
    two concurrent removals each read a count that still contains the other
    target, so both pass. Writing this row inside the transaction gives them a
    document in common, MongoDB aborts one, and the replay re-counts.
    """

    key = models.CharField(max_length=16, unique=True, default="last-admin")
    revision = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.key}: {self.revision}"
