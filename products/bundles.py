from decimal import Decimal

from .models import Bundle


def bundle_discount(qty_by_product, price_by_product, bundles=None):
    """Total saving from bundles that are complete in the cart.

    qty_by_product: {product_id: quantity}; price_by_product: {product_id: unit price}.
    A product counts towards one bundle set at a time, so overlapping bundles can't double count.
    Returns (discount, [(bundle, sets), ...]).
    """
    if bundles is None:
        bundles = Bundle.objects.filter(is_active=True).prefetch_related('products')
    remaining = dict(qty_by_product)
    total = Decimal('0.00')
    applied = []
    for bundle in bundles:
        ids = [p.id for p in bundle.products.all()]
        if len(ids) < 2 or any(remaining.get(pid, 0) <= 0 for pid in ids):
            continue
        saving = sum((price_by_product[pid] for pid in ids), Decimal('0.00')) - bundle.bundle_price
        if saving <= 0:
            continue
        sets = min(remaining[pid] for pid in ids)
        for pid in ids:
            remaining[pid] -= sets
        total += saving * sets
        applied.append((bundle, sets))
    return total, applied
