from django.core.management.base import BaseCommand

from products.models import PriceAlert, Product
from products.services import check_price_alerts, clear_flash_sale_cache


class Command(BaseCommand):
    help = 'Notify customers whose watched products got cheaper (catches flash sales that start on schedule).'

    def handle(self, *args, **options):
        clear_flash_sale_cache()
        products = Product.objects.filter(
            id__in=PriceAlert.objects.filter(notified_at__isnull=True).values('product_id'),
        )
        sent = check_price_alerts(products)
        self.stdout.write(self.style.SUCCESS(f'Sent {sent} price-drop alert(s).'))
