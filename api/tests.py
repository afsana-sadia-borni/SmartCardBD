from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from orders.models import Coupon, Order
from products.models import Category, FlashSale, Product, ProductVariant

SHIPPING = {
    'full_name': 'Rahim Uddin', 'phone': '01712345678', 'district': 'Dhaka', 'upazila': 'Mirpur (Dhaka City)',
    'area': 'Mirpur', 'address_line': 'House 1',
}


class ApiTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.phones = Category.objects.create(name='Phones')
        self.phone = Product.objects.create(category=self.phones, title='Galaxy A15', brand='Samsung',
                                            price=Decimal('20000'), stock=5, description='x')
        self.case = Product.objects.create(category=self.phones, title='Phone case', brand='Generic',
                                           price=Decimal('500'), stock=50, description='x')
        self.user = User.objects.create_user('buyer', 'buyer@example.com', 'Str0ng-pass!')

    def login(self):
        response = self.client.post(reverse('api_token'), {'email': 'buyer@example.com', 'password': 'Str0ng-pass!'})
        self.assertEqual(response.status_code, 200)
        return {'HTTP_AUTHORIZATION': 'Bearer ' + response.json()['access']}

    def order(self, auth, **data):
        body = {'items': [{'product_id': self.phone.id, 'quantity': 1}], **SHIPPING, **data}
        return self.client.post(reverse('api-order-list'), body, content_type='application/json', **auth)


class ProductApiTests(ApiTestCase):
    def test_list_search_and_sort(self):
        data = self.client.get(reverse('api_products'), {'q': 'galaxy'}).json()
        self.assertEqual([p['title'] for p in data['results']], ['Galaxy A15'])
        data = self.client.get(reverse('api_products'), {'sort': 'price_asc'}).json()
        self.assertEqual([p['title'] for p in data['results']], ['Phone case', 'Galaxy A15'])
        self.assertTrue(data['results'][0]['url'].startswith('http://testserver/'))

    def test_detail_has_variants_and_hides_inactive(self):
        ProductVariant.objects.create(product=self.phone, storage='128GB', stock=3)
        ProductVariant.objects.create(product=self.phone, storage='256GB', stock=2, is_active=False)
        data = self.client.get(reverse('api_product_detail', args=[self.phone.slug])).json()
        self.assertEqual([v['label'] for v in data['variants']], ['128GB'])
        self.phone.is_active = False
        self.phone.save()
        self.assertEqual(self.client.get(reverse('api_product_detail', args=[self.phone.slug])).status_code, 404)

    def test_docs_and_schema(self):
        self.assertEqual(self.client.get(reverse('api_docs')).status_code, 200)
        self.assertContains(self.client.get(reverse('api_schema')), 'SmartCart BD API')


class AuthApiTests(ApiTestCase):
    def test_orders_need_login_and_bad_password_is_rejected(self):
        self.assertEqual(self.client.get(reverse('api-order-list')).status_code, 401)
        bad = self.client.post(reverse('api_token'), {'email': 'buyer@example.com', 'password': 'nope'})
        self.assertEqual(bad.status_code, 401)

    def test_profile(self):
        data = self.client.get(reverse('api_me'), **self.login()).json()
        self.assertEqual(data['email'], 'buyer@example.com')
        self.assertIn('?ref=', data['referral_url'])


class OrderApiTests(ApiTestCase):
    def test_place_order_uses_server_prices_and_reduces_stock(self):
        auth = self.login()
        response = self.order(auth, coupon_code='', gift_wrap=True)
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        order = Order.objects.get(order_number=data['order_number'])
        self.assertEqual(order.user, self.user)
        self.assertEqual(order.email, 'buyer@example.com')
        self.assertEqual(order.subtotal, Decimal('20000'))
        self.assertEqual(Decimal(data['total']), Decimal('20000') + order.shipping_cost + order.gift_wrap_cost)
        self.phone.refresh_from_db()
        self.assertEqual(self.phone.stock, 4)
        # Shows up in the list and the detail, with an invoice link.
        listed = self.client.get(reverse('api-order-list'), **auth).json()
        self.assertEqual(listed['results'][0]['order_number'], order.order_number)
        self.assertIn('/invoice.pdf', listed['results'][0]['invoice_url'])

    def test_stock_and_address_are_validated(self):
        auth = self.login()
        too_many = self.order(auth, items=[{'product_id': self.phone.id, 'quantity': 6}])
        self.assertEqual(too_many.status_code, 400)
        self.assertIn('Only 5', too_many.json()['detail'])
        wrong_upazila = self.order(auth, upazila='Dumuria')
        self.assertEqual(wrong_upazila.status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_coupon_and_flash_sale(self):
        Coupon.objects.create(code='SAVE100', discount_type=Coupon.FLAT, value=100,
                              valid_to=timezone.now() + timedelta(days=1))
        sale = FlashSale.objects.create(discount_percent=10, ends_at=timezone.now() + timedelta(hours=1))
        sale.products.add(self.phone)
        response = self.order(self.login(), coupon_code='save100')
        self.assertEqual(response.status_code, 201, response.content)
        order = Order.objects.get()
        self.assertEqual((order.subtotal, order.discount), (Decimal('18000.00'), Decimal('100.00')))
        self.assertEqual(self.order(self.login(), coupon_code='NOPE').status_code, 400)

    def test_cannot_see_other_peoples_orders(self):
        self.order(self.login())
        other = User.objects.create_user('other', 'other@example.com', 'Str0ng-pass!')
        response = self.client.post(reverse('api_token'), {'email': other.email, 'password': 'Str0ng-pass!'})
        auth = {'HTTP_AUTHORIZATION': 'Bearer ' + response.json()['access']}
        number = Order.objects.get().order_number
        self.assertEqual(self.client.get(reverse('api-order-detail', args=[number]), **auth).status_code, 404)
