from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase

from orders.models import Order, OrderItem
from products.models import Category, Product

from .engine import bought_together, similar_products


class RecommendationTests(TestCase):
    def setUp(self):
        cache.clear()
        phones = Category.objects.create(name='Phones')
        audio = Category.objects.create(name='Audio')

        def make(title, category, description):
            return Product.objects.create(category=category, title=title, description=description,
                                          price=Decimal('100'), stock=10)

        self.galaxy = make('Samsung Galaxy A15', phones, 'Android smartphone with AMOLED display and camera')
        self.galaxy_s = make('Samsung Galaxy S23', phones, 'Flagship Android smartphone with great camera')
        self.redmi = make('Xiaomi Redmi Note', phones, 'Android smartphone, fast charging')
        self.earbuds = make('Wireless Earbuds', audio, 'Bluetooth earbuds with deep bass')
        self.speaker = make('Bluetooth Speaker', audio, 'Portable wireless speaker')

    def test_similar_products_prefers_related_text(self):
        result = similar_products(self.galaxy, limit=2)
        self.assertEqual(result[0], self.galaxy_s)
        self.assertNotIn(self.galaxy, result)
        self.assertNotIn(self.speaker, result)

    def test_inactive_products_not_recommended(self):
        Product.objects.filter(pk=self.galaxy_s.pk).update(is_active=False)
        self.assertNotIn(self.galaxy_s, similar_products(self.galaxy))

    def test_bought_together(self):
        for extra in (self.earbuds, self.earbuds, self.speaker):
            order = Order.objects.create(full_name='x', email='x@example.com', phone='01712345678',
                                         district='Dhaka', area='a', address_line='b', subtotal=0,
                                         shipping_cost=0, total=0)
            for product in (self.galaxy, extra):
                OrderItem.objects.create(order=order, product=product, product_title=product.title,
                                         price=product.price, quantity=1)
        self.assertEqual(bought_together(self.galaxy), [self.earbuds, self.speaker])
