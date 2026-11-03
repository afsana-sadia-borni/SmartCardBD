import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from .images import variant_name, webp_url
from .models import Category, FlashSale, Product
from .templatetags.shop_tags import webp


class FlashSaleSortTests(TestCase):
    def setUp(self):
        cache.clear()
        category = Category.objects.create(name='Audio')
        self.speaker = Product.objects.create(category=category, title='Speaker', price=Decimal('3000'), stock=5,
                                              description='x')
        self.earbuds = Product.objects.create(category=category, title='Earbuds', price=Decimal('2000'), stock=5,
                                              description='x')

    def titles(self, **params):
        return [p.title for p in self.client.get(reverse('product_list'), params).context['products']]

    def test_price_sort_and_filter_use_flash_sale_price(self):
        self.assertEqual(self.titles(sort='price_asc'), ['Earbuds', 'Speaker'])
        sale = FlashSale.objects.create(discount_percent=50, ends_at=timezone.now() + timedelta(hours=1))
        sale.products.add(self.speaker)  # ৳3,000 -> ৳1,500
        self.assertEqual(self.titles(sort='price_asc'), ['Speaker', 'Earbuds'])
        self.assertEqual(self.titles(max_price=1600), ['Speaker'])

    def test_annotation_matches_final_price(self):
        self.speaker.discount_price = Decimal('2799.99')
        self.speaker.save()
        sale = FlashSale.objects.create(discount_percent=7, ends_at=timezone.now() + timedelta(hours=1))
        sale.products.add(self.earbuds)
        for product in Product.objects.with_effective_price():
            self.assertEqual(product.effective_price, product.final_price)

    def test_finished_flash_sale_is_ignored(self):
        sale = FlashSale.objects.create(discount_percent=50, starts_at=timezone.now() - timedelta(hours=2),
                                        ends_at=timezone.now() - timedelta(hours=1))
        sale.products.add(self.speaker)
        self.assertEqual(self.titles(sort='price_asc'), ['Earbuds', 'Speaker'])


class WebpTests(TestCase):
    def setUp(self):
        cache.clear()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)

    def photo(self, size=(1200, 900)):
        buffer = BytesIO()
        Image.new('RGB', size, 'navy').save(buffer, 'JPEG')
        return SimpleUploadedFile('phone.jpg', buffer.getvalue(), content_type='image/jpeg')

    def test_upload_creates_small_webp_copies(self):
        with override_settings(MEDIA_ROOT=self.media), self.captureOnCommitCallbacks(execute=True):
            product = Product.objects.create(category=Category.objects.create(name='Phones'), title='Phone',
                                             price=1, stock=1, description='x', image=self.photo())
        with override_settings(MEDIA_ROOT=self.media):
            url = webp(product.image.url, 400)
            self.assertTrue(url.endswith('.w400.webp'))
            with Image.open(f'{self.media}/{variant_name(product.image.name, 400)}') as small:
                self.assertEqual((small.format, small.width), ('WEBP', 400))
            # Never upscaled: the 1600 copy keeps the original width.
            with Image.open(f'{self.media}/{variant_name(product.image.name, 1600)}') as large:
                self.assertEqual(large.width, 1200)

    def test_falls_back_to_original(self):
        self.assertEqual(webp_url('/media/products/missing.jpg', 400), '/media/products/missing.jpg')
        self.assertEqual(webp_url('/static/img/no-image.svg', 400), '/static/img/no-image.svg')
        self.assertIsNone(webp_url(None, 400))
