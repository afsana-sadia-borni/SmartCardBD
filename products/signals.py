from django.db import transaction
from django.db.models import Sum
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from .models import Banner, FlashSale, Product, ProductImage, ProductVariant, ReviewImage
from .services import check_price_alerts, clear_flash_sale_cache
from .tasks import make_webp_images


@receiver([post_save, post_delete], sender=FlashSale)
def flash_sale_changed(sender, instance, **kwargs):
    clear_flash_sale_cache()


@receiver(m2m_changed, sender=FlashSale.products.through)
def flash_sale_products_changed(sender, instance, action, **kwargs):
    if action.startswith('post_'):
        clear_flash_sale_cache()
        if isinstance(instance, FlashSale) and instance.is_active:
            products = list(instance.products.all())
            transaction.on_commit(lambda: check_price_alerts(products))


@receiver(post_save, sender=Product)
def product_saved(sender, instance, **kwargs):
    transaction.on_commit(lambda: check_price_alerts([instance]))


@receiver([post_save, post_delete], sender=ProductVariant)
def sync_product_stock(sender, instance, **kwargs):
    """A product with variants shows the total stock of its active variants."""
    total = ProductVariant.objects.filter(product_id=instance.product_id, is_active=True).aggregate(s=Sum('stock'))['s']
    if total is not None:
        Product.objects.filter(pk=instance.product_id).update(stock=total)


@receiver(post_save, sender=Product)
@receiver(post_save, sender=ProductImage)
@receiver(post_save, sender=Banner)
@receiver(post_save, sender=ReviewImage)
def make_webp_copies(sender, instance, **kwargs):
    """Make the small WebP copies of a new or changed image in the background."""
    name = instance.image.name if instance.image else ''
    if name:
        transaction.on_commit(lambda: make_webp_images.delay(name))
