from .models import Store


def all_store_ids():
    """Public read for other contexts. Returns ids, never Store instances."""
    return Store.objects.values_list("pk", flat=True)
