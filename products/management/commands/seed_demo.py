from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from orders.models import Coupon
from products.models import Category, Product

DEMO_CATALOG = {
    'Mobile Phones': [
        ('Samsung Galaxy A15', 'Samsung', 21999, 19999, 25,
         '6.5" Super AMOLED display, 50MP triple camera, 5000mAh battery and 8GB RAM. Android smartphone with 2 years of OS updates.'),
        ('Xiaomi Redmi Note 13', 'Xiaomi', 24999, None, 18,
         '6.67" AMOLED 120Hz display, 108MP camera, 33W fast charging. Great value Android smartphone.'),
        ('Realme C67', 'Realme', 17999, 16499, 3,
         'Budget smartphone with 108MP camera, 5000mAh battery and 33W SUPERVOOC fast charging.'),
        ('iPhone 13 128GB', 'Apple', 89999, 84999, 6,
         'A15 Bionic chip, dual 12MP camera system, Super Retina XDR display. Official Apple smartphone.'),
    ],
    'Laptops': [
        ('HP 15s Ryzen 5 Laptop', 'HP', 62000, 58500, 7,
         'AMD Ryzen 5 7520U, 8GB RAM, 512GB SSD, 15.6" FHD display. Lightweight laptop for study and office work.'),
        ('Lenovo IdeaPad Slim 3 i5', 'Lenovo', 72500, None, 5,
         'Intel Core i5 12th gen, 16GB RAM, 512GB SSD, 15.6" FHD IPS display. Slim laptop with backlit keyboard.'),
        ('ASUS VivoBook 15 i3', 'ASUS', 49900, 46900, 0,
         'Intel Core i3, 8GB RAM, 256GB SSD, 15.6" display. Affordable everyday laptop for students.'),
    ],
    'Accessories': [
        ('Anker 20W USB-C Fast Charger', 'Anker', 1650, 1399, 60,
         'PowerIQ 3.0 USB-C fast charger for iPhone and Android smartphones. Compact and travel friendly.'),
        ('Baseus Silicone Phone Cover', 'Baseus', 650, None, 80,
         'Soft silicone protective case for smartphones. Shock-absorbing corners and raised camera edge.'),
        ('Logitech M331 Silent Mouse', 'Logitech', 1950, 1750, 30,
         'Wireless silent mouse for laptop and desktop. 90% less click noise, 24 month battery life.'),
        ('Xiaomi 20000mAh Power Bank', 'Xiaomi', 2800, 2499, 4,
         'High capacity power bank with 18W fast charging. Charge smartphones and accessories on the go.'),
    ],
    'Audio': [
        ('JBL Tune 520BT Headphones', 'JBL', 6500, 5490, 15,
         'Wireless on-ear headphones with JBL Pure Bass sound, 57 hours battery and multipoint Bluetooth connection.'),
        ('Soundcore R50i Earbuds', 'Anker', 2200, 1890, 40,
         'True wireless Bluetooth earbuds with deep bass, 30 hours playtime and IPX5 water resistance.'),
        ('Xiaomi Bluetooth Speaker', 'Xiaomi', 3500, None, 12,
         'Portable wireless Bluetooth speaker with 16W stereo sound and IP67 waterproof design.'),
    ],
    "Men's Fashion": [
        ('Cotton Panjabi - Navy Blue', 'Aarong', 3200, 2750, 20,
         'Premium cotton panjabi with embroidered collar. Comfortable traditional wear for Eid and festivals.'),
        ('Classic Fit Polo Shirt', 'Yellow', 1450, None, 35,
         '100% cotton pique polo shirt, classic fit. Breathable everyday casual wear.'),
        ('Leather Formal Shoes', 'Bata', 4500, 3990, 9,
         'Genuine leather formal shoes with cushioned insole. Perfect for office and formal occasions.'),
    ],
}


class Command(BaseCommand):
    help = 'Create demo categories, products and a WELCOME10 coupon (safe to run more than once).'

    @transaction.atomic
    def handle(self, *args, **options):
        created = 0
        for i, (category_name, items) in enumerate(DEMO_CATALOG.items()):
            category, _ = Category.objects.get_or_create(name=category_name)
            for j, (title, brand, price, sale, stock, description) in enumerate(items):
                _, was_created = Product.objects.get_or_create(
                    title=title,
                    defaults={
                        'category': category,
                        'brand': brand,
                        'price': Decimal(price),
                        'discount_price': Decimal(sale) if sale else None,
                        'stock': stock,
                        'description': description,
                        'is_featured': j == 0 or (i + j) % 3 == 0,
                    },
                )
                created += was_created

        Coupon.objects.get_or_create(
            code='WELCOME10',
            defaults={
                'discount_type': Coupon.PERCENT,
                'value': Decimal('10'),
                'max_discount': Decimal('500'),
                'min_order_amount': Decimal('1000'),
                'valid_to': timezone.now() + timedelta(days=365),
            },
        )
        self.stdout.write(self.style.SUCCESS(
            f'Demo data ready: {created} new products. Try coupon WELCOME10 on orders over ৳1,000.'
        ))
