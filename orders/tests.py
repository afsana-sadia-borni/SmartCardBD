from datetime import timedelta
from io import StringIO
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Address
from products.models import Category, Product

from .models import Coupon, Order
from .services import CheckoutError, calculate_shipping, cancel_order, mark_order_paid, release_unpaid_orders

SHIPPING = {
    'full_name': 'Rahim Uddin', 'email': 'rahim@example.com', 'phone': '01712345678',
    'district': 'Dhaka', 'area': 'Mirpur', 'address_line': 'House 1, Road 2', 'payment_method': 'cod',
}


class CheckoutTestCase(TestCase):
    def setUp(self):
        category = Category.objects.create(name='Phones')
        self.phone = Product.objects.create(category=category, title='Phone', price=Decimal('800'), stock=5,
                                            description='x')
        self.case = Product.objects.create(category=category, title='Case', price=Decimal('100'), stock=2,
                                           description='x')

    def add(self, product, qty):
        self.client.post(reverse('cart_add'), {'product_id': product.id, 'quantity': qty})

    def checkout(self, **overrides):
        return self.client.post(reverse('checkout'), {**SHIPPING, **overrides})


class ShippingTests(TestCase):
    @override_settings(SHIPPING_INSIDE_DHAKA=60, SHIPPING_OUTSIDE_DHAKA=120, FREE_SHIPPING_MIN=2000)
    def test_rates(self):
        self.assertEqual(calculate_shipping(Decimal('500'), 'Dhaka'), 60)
        self.assertEqual(calculate_shipping(Decimal('500'), 'Sylhet'), 120)
        self.assertEqual(calculate_shipping(Decimal('2000'), 'Sylhet'), 0)


class PlaceOrderTests(CheckoutTestCase):
    def test_guest_cod_checkout(self):
        self.add(self.phone, 2)
        self.add(self.case, 1)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.checkout()

        order = Order.objects.get()
        self.assertRedirects(response, reverse('order_success', args=[order.order_number]))
        self.assertIsNone(order.user)
        self.assertEqual(order.subtotal, Decimal('1700'))
        self.assertEqual(order.shipping_cost, Decimal('60'))
        self.assertEqual(order.total, Decimal('1760'))
        self.assertEqual(order.items.count(), 2)

        self.phone.refresh_from_db()
        self.case.refresh_from_db()
        self.assertEqual((self.phone.stock, self.case.stock), (3, 1))

        # Cart is emptied, a confirmation email is sent.
        self.assertEqual(len(self.client.get(reverse('cart_summary')).context['cart']), 0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(order.order_number, mail.outbox[0].subject)

    def test_order_keeps_price_snapshot(self):
        self.add(self.phone, 1)
        self.checkout()
        Product.objects.filter(pk=self.phone.pk).update(price=Decimal('999'), title='Renamed')
        item = Order.objects.get().items.get()
        self.assertEqual((item.price, item.product_title), (Decimal('800'), 'Phone'))

    def test_stock_sold_out_between_cart_and_checkout(self):
        self.add(self.case, 2)
        Product.objects.filter(pk=self.case.pk).update(stock=1)  # someone else bought one
        response = self.checkout()
        self.assertRedirects(response, reverse('cart_summary'))
        self.assertFalse(Order.objects.exists())
        self.case.refresh_from_db()
        self.assertEqual(self.case.stock, 1)

    def test_invalid_phone_rejected(self):
        self.add(self.phone, 1)
        response = self.checkout(phone='12345')
        self.assertEqual(response.status_code, 200)
        self.assertIn('phone', response.context['form'].errors)
        self.assertFalse(Order.objects.exists())

    def test_empty_cart_redirects(self):
        self.assertRedirects(self.client.get(reverse('checkout')), reverse('cart_summary'))

    def test_coupon_applied_and_counted(self):
        coupon = Coupon.objects.create(code='FLAT100', discount_type=Coupon.FLAT, value=Decimal('100'),
                                       valid_to=timezone.now() + timedelta(days=1))
        self.add(self.phone, 1)
        self.client.post(reverse('coupon_apply'), {'code': 'flat100'})
        self.checkout(district='Khulna')
        order = Order.objects.get()
        self.assertEqual(order.discount, Decimal('100'))
        self.assertEqual(order.total, Decimal('820'))  # 800 - 100 + 120
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)

    def test_logged_in_checkout_saves_address(self):
        user = get_user_model().objects.create_user('u', 'u@example.com', 'pass12345!')
        self.client.force_login(user)
        self.add(self.phone, 1)
        self.checkout(save_address='on')
        self.assertEqual(Order.objects.get().user, user)
        address = Address.objects.get(user=user)
        self.assertTrue(address.is_default)


class OrderAccessAndCancelTests(CheckoutTestCase):
    def setUp(self):
        super().setUp()
        self.add(self.phone, 2)
        self.checkout()
        self.order = Order.objects.get()

    def test_guest_can_view_own_order_but_others_cannot(self):
        self.assertEqual(self.client.get(self.order.get_absolute_url()).status_code, 200)
        self.client.logout()
        self.client.cookies.clear()
        self.assertEqual(self.client.get(self.order.get_absolute_url()).status_code, 404)

    def test_user_cannot_view_another_users_order(self):
        owner = get_user_model().objects.create_user('a', 'a@example.com', 'pass12345!')
        Order.objects.filter(pk=self.order.pk).update(user=owner)
        intruder = get_user_model().objects.create_user('b', 'b@example.com', 'pass12345!')
        self.client.force_login(intruder)
        self.assertEqual(self.client.get(self.order.get_absolute_url()).status_code, 404)

    def test_cancel_restores_stock(self):
        self.client.post(reverse('order_cancel', args=[self.order.order_number]))
        self.order.refresh_from_db()
        self.phone.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.phone.stock, 5)

    def test_cannot_cancel_after_confirmation_but_staff_can(self):
        self.order.status = Order.Status.SHIPPED
        self.order.save()
        with self.assertRaises(CheckoutError):
            cancel_order(self.order)
        cancel_order(self.order, by_staff=True)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)

    def test_status_change_sends_email(self):
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.order.status = Order.Status.SHIPPED
            self.order.save()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Shipped', mail.outbox[0].subject)


@override_settings(SSLCOMMERZ_STORE_ID='teststore', SSLCOMMERZ_STORE_PASSWORD='secret')
class OnlinePaymentTests(CheckoutTestCase):
    def setUp(self):
        super().setUp()
        self.add(self.phone, 1)

    @mock.patch('orders.payments.requests.post')
    def test_redirects_to_gateway(self, post):
        post.return_value.json.return_value = {'status': 'SUCCESS', 'GatewayPageURL': 'https://sandbox.example/pay'}
        response = self.checkout(payment_method='sslcommerz')
        self.assertRedirects(response, 'https://sandbox.example/pay', fetch_redirect_response=False)
        sent = post.call_args.kwargs['data']
        order = Order.objects.get()
        self.assertEqual((sent['tran_id'], sent['total_amount']), (order.order_number, str(order.total)))

    def _place_online_order(self):
        with mock.patch('orders.payments.requests.post') as post:
            post.return_value.json.return_value = {'status': 'SUCCESS', 'GatewayPageURL': 'https://x'}
            self.checkout(payment_method='sslcommerz')
        return Order.objects.get()

    def _validation(self, order, **overrides):
        data = {'status': 'VALID', 'tran_id': order.order_number, 'currency_type': 'BDT',
                'currency_amount': str(order.total)}
        data.update(overrides)
        return data

    @mock.patch('orders.payments.requests.get')
    def test_validated_payment_marks_order_paid(self, get):
        order = self._place_online_order()
        get.return_value.json.return_value = self._validation(order)
        response = self.client.post(reverse('payment_success'), {'tran_id': order.order_number, 'val_id': 'v1'})
        self.assertRedirects(response, reverse('order_success', args=[order.order_number]))
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(order.status, Order.Status.CONFIRMED)

    @mock.patch('orders.payments.requests.get')
    def test_amount_mismatch_is_rejected(self, get):
        order = self._place_online_order()
        get.return_value.json.return_value = self._validation(order, currency_amount='1.00')
        self.client.post(reverse('payment_success'), {'tran_id': order.order_number, 'val_id': 'v1'})
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.FAILED)

    @mock.patch('orders.payments.requests.get')
    def test_ipn_is_idempotent(self, get):
        order = self._place_online_order()
        get.return_value.json.return_value = self._validation(order)
        for _ in range(2):
            response = self.client.post(reverse('payment_ipn'), {'tran_id': order.order_number, 'val_id': 'v1'})
            self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)

    def test_failed_payment_keeps_order_for_retry(self):
        order = self._place_online_order()
        self.client.post(reverse('payment_fail'), {'tran_id': order.order_number})
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.FAILED)
        self.assertTrue(order.can_pay_online)


@override_settings(SSLCOMMERZ_STORE_ID='teststore', SSLCOMMERZ_STORE_PASSWORD='secret',
                   UNPAID_ORDER_TIMEOUT_MINUTES=60)
class UnpaidOrderReleaseTests(CheckoutTestCase):
    def place(self, product, qty, payment_method='sslcommerz', age_minutes=90):
        self.client.cookies.clear()
        self.add(product, qty)
        with mock.patch('orders.payments.requests.post') as post:
            post.return_value.json.return_value = {'status': 'SUCCESS', 'GatewayPageURL': 'https://x'}
            self.checkout(payment_method=payment_method)
        order = Order.objects.latest('id')
        Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(minutes=age_minutes))
        return order

    def stock(self, product):
        product.refresh_from_db()
        return product.stock

    def test_only_old_unpaid_online_orders_are_released(self):
        # Every checkout also runs the release, so create all orders first and age them afterwards.
        stale = self.place(self.phone, 1, age_minutes=0)
        recent = self.place(self.phone, 1, age_minutes=10)
        cod = self.place(self.phone, 1, payment_method='cod')
        paid = self.place(self.case, 1)
        mark_order_paid(paid, 'v1')
        Order.objects.filter(pk=stale.pk).update(created_at=timezone.now() - timedelta(minutes=90))
        self.assertEqual(self.stock(self.phone), 2)

        self.assertEqual(release_unpaid_orders(), 1)
        statuses = {o.pk: o.status for o in Order.objects.all()}
        self.assertEqual(statuses[stale.pk], Order.Status.CANCELLED)
        self.assertEqual(statuses[recent.pk], Order.Status.PENDING)
        self.assertEqual(statuses[cod.pk], Order.Status.PENDING)
        self.assertEqual(statuses[paid.pk], Order.Status.CONFIRMED)
        self.assertEqual(self.stock(self.phone), 3)

    def test_checkout_releases_abandoned_stock(self):
        other = Client()
        other.post(reverse('cart_add'), {'product_id': self.case.id, 'quantity': 2})  # B fills a cart first
        self.place(self.case, 2)  # A takes all the stock, then abandons the payment page
        self.assertEqual(self.stock(self.case), 0)

        response = other.post(reverse('checkout'), SHIPPING)  # B checks out later
        order = Order.objects.latest('id')
        self.assertRedirects(response, reverse('order_success', args=[order.order_number]),
                             fetch_redirect_response=False)
        self.assertEqual(order.items.get().quantity, 2)
        self.assertEqual(self.stock(self.case), 0)

    def test_late_payment_revives_order_when_stock_is_available(self):
        order = self.place(self.phone, 2)
        release_unpaid_orders()
        mark_order_paid(order, 'late')
        order.refresh_from_db()
        self.assertEqual((order.status, order.payment_status), (Order.Status.CONFIRMED, Order.PaymentStatus.PAID))
        self.assertEqual(self.stock(self.phone), 3)

    def test_late_payment_without_stock_stays_cancelled_for_refund(self):
        order = self.place(self.case, 2)
        release_unpaid_orders()
        Product.objects.filter(pk=self.case.pk).update(stock=1)  # sold to someone else meanwhile
        mark_order_paid(order, 'late')
        order.refresh_from_db()
        self.assertEqual((order.status, order.payment_status), (Order.Status.CANCELLED, Order.PaymentStatus.PAID))
        self.assertEqual(self.stock(self.case), 1)

    def test_management_command(self):
        self.place(self.phone, 1)
        out = StringIO()
        call_command('release_unpaid_orders', stdout=out)
        self.assertIn('Released 1', out.getvalue())


class DashboardTests(TestCase):
    def test_staff_only(self):
        url = reverse('dashboard')
        self.assertEqual(self.client.get(url).status_code, 302)
        staff = get_user_model().objects.create_user('s', 's@example.com', 'pass12345!', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(url).status_code, 200)
