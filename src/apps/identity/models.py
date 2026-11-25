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
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.BARISTA)
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
