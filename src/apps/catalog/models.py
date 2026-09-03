from django.db import models


class Product(models.Model):

    name = models.CharField(max_length=40, blank=True, default='')
    description = models.CharField(max_length=100, blank=True, default='')
    price = models.CharField(max_length=10, blank=True, default='') # fix it soon, gonna check best option of type

    class Meta:
        verbose_name = 'Product'
        verbose_name_plural = 'Products'

    def __str__(self):
        return 'Name: {}'.format(self.name)