"""Public reads for other contexts.

``inventory`` needs product names, units, and thresholds, and the domain
boundary rule forbids importing ``catalog.models`` from another context. These
three functions are the whole surface it may use.
"""

from bson import ObjectId

from .models import Product


def product_exists(product_id: ObjectId) -> bool:
    """Does this product exist? Used to refuse a stock write for a bad id."""
    return Product.objects.filter(pk=product_id).exists()


def product_labels(product_ids) -> dict:
    """``{product_id_hex: (name, unit)}`` for one page of stock rows.

    One query for the whole batch, which is the manual-batch rule that replaces
    ``prefetch_related()`` on this backend.
    """
    ids = [product_id for product_id in product_ids if product_id is not None]
    if not ids:
        return {}
    rows = Product.objects.filter(pk__in=ids).values_list("pk", "name", "unit")
    return {str(pk): (name, unit) for pk, name, unit in rows}


def product_thresholds(product_ids) -> dict:
    """``{product_id_hex: threshold}``, including products with no threshold.

    A product with ``None`` here is one that is never reported as low.
    """
    ids = [product_id for product_id in product_ids if product_id is not None]
    if not ids:
        return {}
    rows = Product.objects.filter(pk__in=ids).values_list("pk", "low_stock_threshold")
    return {str(pk): threshold for pk, threshold in rows}
