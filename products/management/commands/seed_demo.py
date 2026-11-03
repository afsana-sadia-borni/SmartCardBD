from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from orders.models import Coupon
from products.models import Banner, Bundle, Category, FlashSale, Product, ProductImage, ProductVariant

MEDIA_DIR = Path(__file__).resolve().parents[2] / 'demo_media'

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
        ('Cotton Panjabi', 'Aarong', 3200, 2750, 20,
         'Premium cotton panjabi with embroidered collar. Comfortable traditional wear for Eid and festivals.'),
        ('Classic Fit Polo Shirt', 'Yellow', 1450, None, 35,
         '100% cotton pique polo shirt, classic fit. Breathable everyday casual wear.'),
        ('Leather Formal Shoes', 'Bata', 4500, 3990, 9,
         'Genuine leather formal shoes with cushioned insole. Perfect for office and formal occasions.'),
    ],
}


# Images in demo_media/products are named after the product's original slug.
IMAGE_PREFIX = {
    'Cotton Panjabi': 'cotton-panjabi-navy-blue',
}

# Colour of each gallery image (1-based position), so picking a colour shows its photo.
IMAGE_COLORS = {
    'Classic Fit Polo Shirt': {1: 'Light Blue', 2: 'Navy', 3: 'Purple'},
    'Cotton Panjabi': {1: 'Navy', 2: 'Maroon', 3: 'White'},
}

# (color, size, storage, price, sale price, stock)
VARIANTS = {
    'Classic Fit Polo Shirt': [
        (color, size, '', None, None, stock)
        for color, stocks in [('Light Blue', (6, 8, 4)), ('Navy', (5, 7, 0)), ('Purple', (3, 4, 2))]
        for size, stock in zip(('M', 'L', 'XL'), stocks)
    ],
    'Cotton Panjabi': [
        (color, size, '', None, None, stock)
        for color, stocks in [('Navy', (3, 5, 4, 2)), ('Maroon', (2, 3, 3, 1)), ('White', (4, 4, 2, 0))]
        for size, stock in zip(('38', '40', '42', '44'), stocks)
    ],
    'Leather Formal Shoes': [('', size, '', None, None, stock) for size, stock in
                             [('40', 2), ('41', 3), ('42', 2), ('43', 1), ('44', 1)]],
    'iPhone 13 128GB': [('', '', '128GB', None, None, 4), ('', '', '256GB', 99999, 94999, 2)],
    'Samsung Galaxy A15': [('', '', '128GB', None, None, 15), ('', '', '256GB', 24999, 22999, 10)],
}

BANNERS = [
    ('electronics.jpg', 'Laptops for work & study', 'Ryzen 5 and Core i5 laptops, delivered to your door.',
     '/category/laptops/', 'Shop laptops'),
    ('fashion.jpg', 'The Eid collection is here', 'Panjabi, polo shirts and shoes from top local brands.',
     '/category/mens-fashion/', 'Shop fashion'),
    ('mall.jpg', 'Flash sale: 20% off audio', 'Headphones, earbuds and speakers. Limited time only.',
     '/#flash-sale', 'See the deals'),
]

FLASH_SALE_PRODUCTS = ['JBL Tune 520BT Headphones', 'Soundcore R50i Earbuds', 'Xiaomi Bluetooth Speaker', 'Realme C67']

BUNDLES = [
    ('iPhone starter kit: phone + cover + charger', ['iPhone 13 128GB', 'Baseus Silicone Phone Cover',
                                                     'Anker 20W USB-C Fast Charger'], 500),
    ('Work-from-home set: laptop + silent mouse', ['HP 15s Ryzen 5 Laptop', 'Logitech M331 Silent Mouse'], 700),
]


class Command(BaseCommand):
    help = ('Create demo categories, products (with photos and variants), banners, a flash sale, bundles and '
            'a WELCOME10 coupon. Safe to run more than once.')

    def attach_images(self, product):
        prefix = IMAGE_PREFIX.get(product.title, product.slug)
        files = sorted((MEDIA_DIR / 'products').glob(f'{prefix}-[0-9].jpg'))
        if not files:
            return
        if not product.image:
            with files[0].open('rb') as f:
                product.image.save(files[0].name, File(f), save=True)
        if not product.images.exists():
            colors = IMAGE_COLORS.get(product.title, {})
            for i, path in enumerate(files, start=1):
                if i == 1 and not colors:
                    continue  # already the main image
                with path.open('rb') as f:
                    img = ProductImage(product=product, alt=product.title, color=colors.get(i, ''), sort_order=i)
                    img.image.save(path.name, File(f), save=True)

    def add_variants(self, product):
        if product.variants.exists():
            return
        for color, size, storage, price, sale, stock in VARIANTS.get(product.title, []):
            ProductVariant.objects.create(
                product=product, color=color, size=size, storage=storage,
                price=Decimal(price) if price else None, discount_price=Decimal(sale) if sale else None, stock=stock,
                sku=f'{product.slug[:24]}-{color}{size}{storage}'.replace(' ', '').upper()[:40],
            )

    def add_banners(self):
        if Banner.objects.exists():
            return
        for order, (filename, title, subtitle, link, button) in enumerate(BANNERS, start=1):
            path = MEDIA_DIR / 'banners' / filename
            banner = Banner(title=title, subtitle=subtitle, link_url=link, button_text=button, sort_order=order)
            with path.open('rb') as f:
                banner.image.save(filename, File(f), save=True)

    def add_flash_sale(self):
        if FlashSale.objects.filter(ends_at__gt=timezone.now()).exists():
            return
        sale = FlashSale.objects.create(title='Audio flash sale', discount_percent=20,
                                        ends_at=timezone.now() + timedelta(days=3))
        sale.products.set(Product.objects.filter(title__in=FLASH_SALE_PRODUCTS))

    def add_bundles(self):
        for title, product_titles, saving in BUNDLES:
            if Bundle.objects.filter(title=title).exists():
                continue
            products = list(Product.objects.filter(title__in=product_titles))
            if len(products) != len(product_titles):
                continue
            regular = sum((p.final_price for p in products), Decimal('0'))
            bundle = Bundle.objects.create(title=title, bundle_price=regular - saving)
            bundle.products.set(products)

    @transaction.atomic
    def handle(self, *args, **options):
        # Older demo data used a colour in the panjabi's title; it now has colour options instead.
        Product.objects.filter(title='Cotton Panjabi - Navy Blue').update(title='Cotton Panjabi')
        created = 0
        for i, (category_name, items) in enumerate(DEMO_CATALOG.items()):
            category, _ = Category.objects.get_or_create(name=category_name)
            for j, (title, brand, price, sale, stock, description) in enumerate(items):
                product, was_created = Product.objects.get_or_create(
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
                self.attach_images(product)
                self.add_variants(product)

        self.add_banners()
        self.add_flash_sale()
        self.add_bundles()

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
            f'Demo data ready: {created} new products, with photos, variants, banners, a flash sale and bundles. '
            'Try coupon WELCOME10 on orders over ৳1,000.'
        ))
