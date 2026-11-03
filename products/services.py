from django.core.cache import cache
from django.utils import timezone

from .models import FLASH_SALE_CACHE_KEY, PriceAlert


def clear_flash_sale_cache():
    cache.delete(FLASH_SALE_CACHE_KEY)


def check_price_alerts(products):
    """Tell customers who asked when a product's price has dropped below what it was when they asked."""
    from accounts.services import notify

    sent = 0
    alerts = PriceAlert.objects.filter(product__in=products, notified_at__isnull=True).select_related('product', 'user')
    for alert in alerts:
        product = alert.product
        price = product.final_price
        if price < alert.price_when_set:
            notify(
                alert.user,
                f'Price drop! "{product.title}" is now ৳{price:,.0f} (was ৳{alert.price_when_set:,.0f}).',
                url=product.get_absolute_url(), icon='tag', email_subject=f'Price drop: {product.title}',
            )
            alert.notified_at = timezone.now()
            alert.save(update_fields=['notified_at'])
            sent += 1
    return sent


def send_due_price_alerts():
    """Check every product someone is watching (catches flash sales that start on schedule)."""
    from .models import Product

    clear_flash_sale_cache()
    products = Product.objects.filter(
        id__in=PriceAlert.objects.filter(notified_at__isnull=True).values('product_id'),
    )
    return check_price_alerts(products)
