from django.db import models


class Product(models.Model):
    """One thing that can be stocked or sold.

    Price is optional because a supply such as milk is stocked and never sold.
    Unit is a display label only: no conversion logic exists anywhere in the
    project, so a quantity in litres is nobody else's business.
    """

    name = models.CharField(max_length=40, blank=True, default="")
    description = models.CharField(max_length=100, blank=True, default="")
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    unit = models.CharField(max_length=8, blank=True, default="pcs")
    low_stock_threshold = models.DecimalField(
        max_digits=12, decimal_places=3, null=True, blank=True
    )

    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"

    def __str__(self):
        return f"Name: {self.name}"
