from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from orders.models import Coupon
from products.models import Category, Product

AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}


class CartTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name='Phones')
        self.product = Product.objects.create(
            category=category, title='Phone', price=Decimal('1000'), discount_price=Decimal('900'),
            stock=5, description='x',
        )

    def add(self, qty, product=None):
        return self.client.post(reverse('cart_add'), {'product_id': (product or self.product).id, 'quantity': qty},
                                **AJAX).json()

    def test_add_uses_sale_price(self):
        data = self.add(2)
        self.assertEqual(data['cart_count'], 2)
        self.assertEqual(Decimal(data['total']), Decimal('1800'))

    def test_quantity_capped_at_stock(self):
        data = self.add(50)
        self.assertEqual(data['cart_count'], 5)
        self.assertEqual(data['level'], 'warning')

    def test_out_of_stock_cannot_be_added(self):
        self.product.stock = 0
        self.product.save()
        data = self.add(1)
        self.assertEqual(data['cart_count'], 0)
        self.assertEqual(data['level'], 'error')

    def test_update_and_remove(self):
        self.add(1)
        data = self.client.post(reverse('cart_update'), {'product_id': self.product.id, 'quantity': 3}, **AJAX).json()
        self.assertEqual(data['quantity'], 3)
        self.assertEqual(Decimal(data['item_subtotal']), Decimal('2700'))
        data = self.client.post(reverse('cart_remove'), {'product_id': self.product.id}, **AJAX).json()
        self.assertEqual(data['cart_count'], 0)

    def test_price_change_reflected_in_cart(self):
        self.add(1)
        Product.objects.filter(pk=self.product.pk).update(discount_price=Decimal('500'))
        response = self.client.get(reverse('cart_summary'))
        self.assertEqual(response.context['cart'].get_total(), Decimal('500'))

    def test_deactivated_product_disappears_from_cart(self):
        self.add(1)
        Product.objects.filter(pk=self.product.pk).update(is_active=False)
        response = self.client.get(reverse('cart_summary'))
        self.assertEqual(len(response.context['cart']), 0)

    def test_get_requests_not_allowed(self):
        self.assertEqual(self.client.get(reverse('cart_add')).status_code, 405)

    def test_external_next_url_is_ignored(self):
        response = self.client.post(reverse('cart_add'),
                                    {'product_id': self.product.id, 'next': 'https://evil.example.com/'})
        self.assertRedirects(response, reverse('cart_summary'))


class CouponTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name='Phones')
        self.product = Product.objects.create(category=category, title='Phone', price=Decimal('1000'), stock=10,
                                              description='x')
        self.coupon = Coupon.objects.create(
            code='save10', value=Decimal('10'), max_discount=Decimal('150'), min_order_amount=Decimal('1500'),
            valid_to=timezone.now() + timedelta(days=1),
        )

    def add(self, qty):
        self.client.post(reverse('cart_add'), {'product_id': self.product.id, 'quantity': qty})

    def cart(self):
        return self.client.get(reverse('cart_summary')).context['cart']

    def test_code_is_case_insensitive_and_capped(self):
        self.add(2)  # 2000 -> 10% = 200, capped to 150
        self.client.post(reverse('coupon_apply'), {'code': 'SAVE10'})
        self.assertEqual(self.cart().get_discount(), Decimal('150'))

    def test_minimum_amount(self):
        self.add(1)
        self.client.post(reverse('coupon_apply'), {'code': 'save10'})
        self.assertIsNone(self.cart().coupon)

    def test_coupon_dropped_when_cart_falls_below_minimum(self):
        self.add(2)
        self.client.post(reverse('coupon_apply'), {'code': 'save10'})
        self.client.post(reverse('cart_update'), {'product_id': self.product.id, 'quantity': 1})
        self.assertEqual(self.cart().get_discount(), Decimal('0'))

    def test_expired_and_used_up(self):
        self.assertFalse(Coupon(code='x', value=1, valid_to=timezone.now() - timedelta(seconds=1))
                         .is_valid_for(Decimal('9999'))[0])
        self.assertFalse(Coupon(code='y', value=1, valid_to=timezone.now() + timedelta(days=1),
                                usage_limit=3, used_count=3).is_valid_for(Decimal('9999'))[0])

    def test_flat_discount_never_exceeds_subtotal(self):
        coupon = Coupon(code='z', discount_type=Coupon.FLAT, value=Decimal('5000'),
                        valid_to=timezone.now() + timedelta(days=1))
        self.assertEqual(coupon.calculate_discount(Decimal('1200')), Decimal('1200'))
