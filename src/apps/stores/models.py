from django.db import models


class Store(models.Model):

    name = models.CharField(max_length=40, blank=True, default='')
    address = models.CharField(max_length=100, blank=True, default='')
    postal_code = models.CharField(max_length=10, blank=True, default='')
    # manager = FK to user that is a manager

    class Meta:
        verbose_name = 'Store'
        verbose_name_plural = 'Stores'

    def __str__(self):
        return 'Name: {}'.format(self.name)
        # return 'Name: {}, Manager: {}'.format(self.name, self.bairro) 
