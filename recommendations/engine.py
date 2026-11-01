"""Product recommendations.

* Similar products: content-based. Each product's title, brand, category and
  description become a TF-IDF vector; neighbours are ranked by cosine similarity.
* Frequently bought together: co-occurrence counts from past orders.

The TF-IDF matrix is cached and rebuilt automatically when the catalogue changes.
"""
from collections import Counter

from django.core.cache import cache
from django.db.models import Count, Max
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

from orders.models import Order, OrderItem
from products.models import Product

CACHE_TIMEOUT = 60 * 60


def _catalog_version():
    stats = Product.objects.active().aggregate(n=Count('id'), last=Max('updated_at'))
    return f"{stats['n']}-{stats['last'].timestamp() if stats['last'] else 0}"


def _build_similarity_index():
    rows = list(
        Product.objects.active().values_list('id', 'title', 'brand', 'category__name', 'description')
    )
    if len(rows) < 2:
        return {}
    ids = [r[0] for r in rows]
    # Title, brand and category are repeated to weigh them more than the description.
    docs = [f'{t} {t} {b} {b} {c} {c} {d}' for _, t, b, c, d in rows]
    matrix = TfidfVectorizer(stop_words='english', ngram_range=(1, 2), min_df=1).fit_transform(docs)
    scores = linear_kernel(matrix, matrix)  # TF-IDF rows are L2-normalised, so this is cosine similarity.

    index = {}
    for i, pid in enumerate(ids):
        ranked = scores[i].argsort()[::-1]
        index[pid] = [ids[j] for j in ranked if j != i and scores[i][j] > 0][:12]
    return index


def _similarity_index():
    key = f'recs:similar:{_catalog_version()}'
    index = cache.get(key)
    if index is None:
        index = _build_similarity_index()
        cache.set(key, index, CACHE_TIMEOUT)
    return index


def _preserve_order(ids, limit):
    by_id = {p.id: p for p in Product.objects.active().filter(id__in=ids)}
    return [by_id[i] for i in ids if i in by_id][:limit]


def similar_products(product, limit=4):
    ids = _similarity_index().get(product.id, [])
    result = _preserve_order(ids, limit)
    if len(result) < limit:
        # Not enough text signal yet: top up with the newest products from the same category.
        exclude = {product.id, *(p.id for p in result)}
        result += list(
            Product.objects.active().filter(category=product.category).exclude(id__in=exclude)[:limit - len(result)]
        )
    return result


def bought_together(product, limit=4):
    order_ids = (
        OrderItem.objects.filter(product=product)
        .exclude(order__status=Order.Status.CANCELLED)
        .values_list('order_id', flat=True)
    )
    counts = Counter(
        OrderItem.objects.filter(order_id__in=order_ids)
        .exclude(product=product)
        .exclude(product__isnull=True)
        .values_list('product_id', flat=True)
    )
    return _preserve_order([pid for pid, _ in counts.most_common(limit * 2)], limit)
