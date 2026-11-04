"""Search, filters and sorting for the product list. Shared by the shop pages and the REST API."""
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

SORT_OPTIONS = {
    'newest': (_('Newest'), ['-created_at']),
    'price_asc': (_('Price: Low to High'), ['effective_price', '-created_at']),
    'price_desc': (_('Price: High to Low'), ['-effective_price', '-created_at']),
    'rating': (_('Top Rated'), [F('avg_rating').desc(nulls_last=True), '-review_count', '-created_at']),
}


def _price(params, name):
    try:
        return max(float(params[name]), 0)
    except (KeyError, TypeError, ValueError):
        return None


def filter_products(products, params):
    """Apply ?q=, min_price, max_price, brand, in_stock and sort to a queryset from shop_products().

    Returns (queryset, sort key). Prices compare against the price customers pay now, flash sales included.
    """
    products = products.with_effective_price()
    q = params.get('q', '').strip()
    if q:
        products = products.filter(
            Q(title__icontains=q) | Q(description__icontains=q)
            | Q(brand__icontains=q) | Q(category__name__icontains=q)
        )
    min_price, max_price = _price(params, 'min_price'), _price(params, 'max_price')
    if min_price is not None:
        products = products.filter(effective_price__gte=min_price)
    if max_price is not None:
        products = products.filter(effective_price__lte=max_price)
    brand = params.get('brand', '').strip()
    if brand:
        products = products.filter(brand__iexact=brand)
    if params.get('in_stock'):
        products = products.filter(stock__gt=0)

    sort = params.get('sort', 'newest')
    if sort not in SORT_OPTIONS:
        sort = 'newest'
    return products.order_by(*SORT_OPTIONS[sort][1]), sort
