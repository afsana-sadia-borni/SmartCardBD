from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from products.models import Category, Product

from .courier import sync_steadfast_statuses
from .models import BlockedPhone, Order

SHIPPING = {
    'full_name': 'Rahim Uddin', 'email': 'rahim@example.com', 'phone': '01712345678', 'district': 'Dhaka',
    'upazila': 'Mirpur (Dhaka City)', 'area': 'Mirpur', 'address_line': 'House 1', 'payment_method': 'cod',
}
SMS_ON = {'SMS_API_KEY': 'key', 'SMS_SENDER_ID': 'SHOP'}
STEADFAST_ON = {'STEADFAST_API_KEY': 'k', 'STEADFAST_SECRET_KEY': 's'}


def sms_ok():
    return mock.Mock(**{'json.return_value': {'response_code': 202}})


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.product = Product.objects.create(category=Category.objects.create(name='Audio'), title='Speaker',
                                              price=Decimal('1500'), stock=50, description='x')
        self.owner = User.objects.create_user('o', 'o@example.com', 'x', is_staff=True, is_superuser=True)

    def checkout(self, **extra):
        self.client.post(reverse('cart_add'), {'product_id': self.product.id, 'quantity': extra.pop('qty', 1)})
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse('checkout'), {**SHIPPING, **extra})


class NotificationTests(Base):
    @override_settings(**SMS_ON)
    @mock.patch('core.sms.requests.post', return_value=sms_ok())
    def test_order_texts_and_html_email(self, post):
        self.checkout()
        order = Order.objects.get()
        self.assertIn(order.order_number, post.call_args.kwargs['data']['message'])
        html = mail.outbox[-1].alternatives[0][0]
        self.assertIn(order.order_number, html)
        self.assertIn('<table', html)
        with self.captureOnCommitCallbacks(execute=True):
            order.status = Order.Status.SHIPPED
            order.save()
        self.assertIn('on the way', post.call_args.kwargs['data']['message'])

    @override_settings(**SMS_ON, ACCOUNT_PHONE_VERIFICATION_ENABLED=True)
    @mock.patch('core.sms.requests.post', return_value=sms_ok())
    def test_signup_sends_a_verification_code_when_sms_is_set_up(self, post):
        response = self.client.post(reverse('account_signup'), {
            'full_name': 'Nusrat Jahan', 'phone': '01812345678', 'email': 'n@example.com',
            'password1': 'Str0ng-pass!', 'password2': 'Str0ng-pass!'})
        self.assertRedirects(response, reverse('account_verify_phone'), fetch_redirect_response=False)
        self.assertRegex(post.call_args.kwargs['data']['message'], r'code is \w+')


@override_settings(**STEADFAST_ON)
class CourierTests(Base):
    def steadfast(self, payload, code=200):
        return mock.Mock(status_code=code, **{'json.return_value': payload})

    @mock.patch('orders.courier.requests.request')
    def test_book_from_store_panel_and_follow_to_delivery(self, request):
        self.checkout()
        order = Order.objects.get()
        request.return_value = self.steadfast({'status': 200, 'consignment': {
            'consignment_id': 1424107, 'tracking_code': '15BAEB8A', 'status': 'in_review'}})
        self.client.force_login(self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('store:order_action', args=[order.order_number]), {'action': 'book_steadfast'})
        sent = request.call_args.kwargs
        self.assertEqual(sent['headers']['Api-Key'], 'k')
        self.assertEqual((sent['json']['invoice'], sent['json']['cod_amount']), (order.order_number, float(order.total)))
        order.refresh_from_db()
        self.assertEqual((order.status, order.courier_tracking_code), ('shipped', '15BAEB8A'))
        self.assertIn('15BAEB8A', order.courier_tracking_url)
        self.assertIn('15BAEB8A', mail.outbox[-1].body)  # the shipped email has the tracking link

        request.return_value = self.steadfast({'status': 200, 'delivery_status': 'delivered'})
        self.assertEqual(sync_steadfast_statuses(), 1)
        order.refresh_from_db()
        self.assertEqual((order.status, order.payment_status), ('delivered', 'paid'))

    @mock.patch('orders.courier.requests.request')
    def test_booking_errors_are_shown_and_nothing_changes(self, request):
        self.checkout()
        order = Order.objects.get()
        request.return_value = self.steadfast({'status': 400, 'message': 'Invalid phone'}, code=400)
        self.client.force_login(self.owner)
        response = self.client.post(reverse('store:order_action', args=[order.order_number]),
                                    {'action': 'book_steadfast'}, follow=True)
        self.assertContains(response, 'Invalid phone')
        order.refresh_from_db()
        self.assertEqual(order.status, 'pending')

    def test_manual_tracking_shows_to_the_customer(self):
        self.checkout()
        order = Order.objects.get()
        self.client.force_login(self.owner)
        self.client.post(reverse('store:order_action', args=[order.order_number]), {
            'action': 'set_tracking', 'courier_name': 'Pathao', 'tracking_code': 'PTH123',
            'tracking_link': 'https://merchant.pathao.com/tracking?consignment_id=PTH123'})
        order.refresh_from_db()
        order.status = Order.Status.SHIPPED
        order.save()
        self.client.logout()
        page = self.client.post(reverse('track_order'), {'order_number': order.order_number, 'phone': '01712345678'})
        self.assertContains(page, 'Track with Pathao')


class BulkTests(Base):
    def test_bulk_confirm_and_packing_slips(self):
        for _ in range(3):
            self.checkout()
        numbers = list(Order.objects.values_list('order_number', flat=True))
        Order.objects.filter(order_number=numbers[0]).update(status=Order.Status.DELIVERED)
        self.client.force_login(self.owner)
        response = self.client.post(reverse('store:orders_bulk'), {'orders': numbers, 'action': 'confirm'}, follow=True)
        self.assertEqual(Order.objects.filter(status='confirmed').count(), 2)
        self.assertContains(response, 'Skipped')
        slips = self.client.post(reverse('store:orders_bulk'), {'orders': numbers[1:], 'action': 'slips'}, follow=True)
        self.assertContains(slips, 'COLLECT:', count=2)

    def test_customers_cannot_use_bulk_actions(self):
        self.checkout()
        self.client.force_login(User.objects.create_user('c', 'c@example.com', 'x'))
        number = Order.objects.get().order_number
        self.assertEqual(self.client.post(reverse('store:orders_bulk'), {'orders': [number], 'action': 'confirm'}).status_code, 404)


class FakeOrderTests(Base):
    def test_blocked_number_cannot_use_cod(self):
        BlockedPhone.objects.create(phone='01712345678')
        response = self.checkout()
        self.assertContains(response, 'available for this number')
        self.assertFalse(Order.objects.exists())

    def test_risky_orders_are_flagged_for_staff(self):
        for _ in range(3):
            self.checkout()
        risky = self.checkout()
        self.assertEqual(risky.status_code, 302)
        order = Order.objects.order_by('-created_at').first()
        self.assertTrue(any('last 24 hours' in f for f in order.risk_flags))
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse('store:orders')), '⚠ Check')
        self.client.post(reverse('store:order_action', args=[order.order_number]), {'action': 'block_phone'})
        self.assertTrue(BlockedPhone.objects.filter(phone='01712345678').exists())

    @override_settings(**SMS_ON, COD_OTP='always')
    @mock.patch('core.sms.requests.post', return_value=sms_ok())
    def test_cod_order_needs_the_sms_code(self, post):
        response = self.checkout()
        self.assertRedirects(response, reverse('checkout_verify'))
        self.assertFalse(Order.objects.exists())
        code = post.call_args.kwargs['data']['message'][:6]
        wrong = self.client.post(reverse('checkout_verify'), {'code': '000000' if code != '000000' else '111111'})
        self.assertContains(wrong, 'not right')
        with self.captureOnCommitCallbacks(execute=True):
            done = self.client.post(reverse('checkout_verify'), {'code': code})
        order = Order.objects.get()
        self.assertRedirects(done, reverse('order_success', args=[order.order_number]), fetch_redirect_response=False)
        self.assertIn('Phone confirmed with an SMS code', order.risk_flags)
