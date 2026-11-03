from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomerProfile, Notification, get_profile
from products.models import Category, Product

from .models import Coupon, Order, ReturnRequest
from .services import calculate_shipping, cancel_order, delivery_info

SHIPPING = {
    'full_name': 'Rahim Uddin', 'email': 'rahim@example.com', 'phone': '01712345678', 'district': 'Dhaka',
    'upazila': 'Mirpur (Dhaka City)', 'area': 'Mirpur', 'address_line': 'House 1', 'payment_method': 'cod',
}


class OrderTestCase(TestCase):
    def setUp(self):
        cache.clear()
        category = Category.objects.create(name='Gadgets')
        self.product = Product.objects.create(category=category, title='Speaker', price=Decimal('1500'), stock=10,
                                              description='x')
        self.user = User.objects.create_user('buyer', 'buyer@example.com', 'pw-Str0ng!')

    def buy(self, qty=1, login=True, **extra):
        if login:
            self.client.force_login(self.user)
        self.client.post(reverse('cart_add'), {'product_id': self.product.id, 'quantity': qty})
        self.client.post(reverse('checkout'), {**SHIPPING, **extra})
        return Order.objects.latest('created_at')

    def deliver(self, order):
        order.status = Order.Status.DELIVERED
        order.save()
        order.refresh_from_db()
        return order


class DeliveryZoneTests(OrderTestCase):
    def test_default_zones_set_charge_and_estimate(self):
        self.assertEqual(delivery_info('Dhaka'), (Decimal('60.00'), '1-2 days'))
        self.assertEqual(delivery_info('Gazipur'), (Decimal('100.00'), '2-3 days'))
        self.assertEqual(delivery_info('Sylhet'), (Decimal('120.00'), '3-5 days'))
        self.assertEqual(calculate_shipping(Decimal('500'), 'Gazipur'), Decimal('100.00'))

    def test_order_stores_upazila_and_estimate(self):
        order = self.buy()
        self.assertEqual((order.upazila, order.delivery_estimate), ('Mirpur (Dhaka City)', '1-2 days'))

    def test_upazila_must_match_district(self):
        self.client.post(reverse('cart_add'), {'product_id': self.product.id, 'quantity': 1})
        response = self.client.post(reverse('checkout'), {**SHIPPING, 'upazila': 'Dumuria'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.exists())


class CashOnDeliveryTests(OrderTestCase):
    def test_delivered_cod_order_is_paid_whoever_marks_it(self):
        order = self.deliver(self.buy())  # plain save(), like the Django admin
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        other = self.buy()
        other.status = Order.Status.DELIVERED
        other.save(update_fields=['status', 'updated_at'])  # like the admin's bulk action
        other.refresh_from_db()
        self.assertEqual(other.payment_status, Order.PaymentStatus.PAID)


class GiftWrapAndPointsTests(OrderTestCase):
    def test_gift_wrap_adds_charge(self):
        order = self.buy(gift_wrap='on')
        self.assertTrue(order.gift_wrap)
        self.assertEqual(order.total, Decimal('1500') + order.shipping_cost + Decimal('50'))

    def test_points_earned_on_delivery_and_spent_at_checkout(self):
        order = self.deliver(self.buy(qty=2))  # ৳3,000 of goods -> 30 points
        self.assertEqual(get_profile(self.user).points, 30)
        self.assertEqual(order.points_earned, 30)
        self.deliver(order)  # saving again must not double count
        self.assertEqual(get_profile(self.user).points, 30)

        CustomerProfile.objects.filter(user=self.user).update(points=250)
        second = self.buy(use_points='on')
        self.assertEqual((second.points_used, second.points_discount), (200, Decimal('100')))
        self.assertEqual(get_profile(self.user).points, 50)

        cancel_order(second)
        self.assertEqual(get_profile(self.user).points, 250)

    def test_status_change_creates_notification(self):
        order = self.buy()
        order.status = Order.Status.SHIPPED
        order.save()
        self.assertTrue(Notification.objects.filter(user=self.user, message__contains='shipped').exists())


class ReferralTests(OrderTestCase):
    def test_both_people_get_a_coupon_after_first_delivery(self):
        friend = User.objects.create_user('friend', 'friend@example.com', 'pw-Str0ng!')
        CustomerProfile.objects.filter(user=self.user).update(referred_by=friend)
        self.deliver(self.buy())
        coupons = Coupon.objects.filter(user__in=[self.user, friend])
        self.assertEqual(coupons.count(), 2)
        self.assertTrue(all(c.value == Decimal('100') and c.usage_limit == 1 for c in coupons))
        # Only once.
        self.deliver(self.buy())
        self.assertEqual(Coupon.objects.filter(user__in=[self.user, friend]).count(), 2)

    def test_personal_coupon_only_works_for_its_owner(self):
        friend = User.objects.create_user('friend', 'friend@example.com', 'pw-Str0ng!')
        coupon = Coupon.objects.create(code='MINE100', discount_type=Coupon.FLAT, value=100, user=friend,
                                       valid_to=timezone.now() + timedelta(days=1))
        self.assertFalse(coupon.is_valid_for(Decimal('1000'), self.user)[0])
        self.assertTrue(coupon.is_valid_for(Decimal('1000'), friend)[0])


class TrackOrderTests(OrderTestCase):
    def test_guest_can_track_with_number_and_phone(self):
        order = self.buy(login=False)
        self.client.logout()
        ok = self.client.post(reverse('track_order'), {'order_number': order.order_number, 'phone': '01712345678'})
        self.assertContains(ok, order.order_number)
        self.assertContains(ok, 'order-steps')
        wrong = self.client.post(reverse('track_order'), {'order_number': order.order_number, 'phone': '01811111111'})
        self.assertContains(wrong, 'No order matches')

    def test_tracking_is_rate_limited(self):
        for _ in range(11):
            response = self.client.post(reverse('track_order'), {'order_number': 'X', 'phone': '01712345678'},
                                        follow=True)
        self.assertContains(response, 'Too many attempts')


class ReturnRequestTests(OrderTestCase):
    def test_return_only_after_delivery_and_decision_notifies(self):
        order = self.buy()
        url = reverse('return_request', args=[order.order_number])
        self.client.post(url, {'reason': 'damaged', 'details': 'Broken box'})
        self.assertFalse(ReturnRequest.objects.exists())

        self.deliver(order)
        self.client.post(url, {'reason': 'damaged', 'details': 'Broken box'})
        rr = ReturnRequest.objects.get()
        rr.status = ReturnRequest.Status.APPROVED
        rr.save()
        self.assertTrue(Notification.objects.filter(user=self.user, message__contains='Approved').exists())

    def test_return_window_closes(self):
        order = self.deliver(self.buy())
        order.history.update(history_date=timezone.now() - timedelta(days=30))
        self.assertFalse(Order.objects.get(pk=order.pk).can_request_return)


class SalesReportTests(OrderTestCase):
    def test_csv_for_staff_only(self):
        self.buy()
        self.assertEqual(self.client.get(reverse('sales_report_csv')).status_code, 302)
        self.user.is_staff = True
        self.user.save()
        response = self.client.get(reverse('sales_report_csv'))
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('Rahim Uddin', response.content.decode('utf-8-sig'))
