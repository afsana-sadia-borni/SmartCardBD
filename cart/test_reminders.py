from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Subscriber
from products.models import Category, Product

from .cart import CART_UPDATED_KEY
from .services import send_abandoned_cart_reminders

AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}


class AbandonedCartTests(TestCase):
    def setUp(self):
        cache.clear()
        category = Category.objects.create(name='Audio')
        self.product = Product.objects.create(category=category, title='Speaker', price=Decimal('1500'), stock=5,
                                              description='x')

    def fill_cart(self):
        self.client.post(reverse('cart_add'), {'product_id': self.product.id, 'quantity': 1})

    def age_cart(self, hours=25):
        session = Session.objects.get(session_key=self.client.session.session_key)
        data = session.get_decoded()
        data[CART_UPDATED_KEY] = (timezone.now() - timedelta(hours=hours)).isoformat()
        session.session_data = Session.objects.encode(data)
        session.save()

    def test_guest_who_typed_email_gets_one_reminder(self):
        self.fill_cart()
        self.assertTrue(self.client.post(reverse('cart_remember_email'), {'email': 'Guest@Example.com'}, **AJAX)
                        .json()['ok'])
        self.age_cart()
        self.assertEqual(send_abandoned_cart_reminders(), 1)
        self.assertEqual(mail.outbox[0].to, ['guest@example.com'])
        self.assertIn('http://localhost:8000/cart/', mail.outbox[0].body)
        self.assertEqual(send_abandoned_cart_reminders(), 0)  # only once

    def test_logged_in_user_gets_reminder(self):
        user = User.objects.create_user('u', 'u@example.com', 'x')
        self.client.force_login(user)
        self.fill_cart()
        self.age_cart()
        self.assertEqual(send_abandoned_cart_reminders(), 1)
        self.assertEqual(mail.outbox[0].to, ['u@example.com'])

    def test_no_reminder_for_fresh_carts_unsubscribed_or_bad_email(self):
        self.fill_cart()
        self.assertEqual(self.client.post(reverse('cart_remember_email'), {'email': 'nope'}, **AJAX).status_code, 400)
        self.client.post(reverse('cart_remember_email'), {'email': 'gone@example.com'}, **AJAX)
        self.assertEqual(send_abandoned_cart_reminders(), 0)  # cart is fresh
        Subscriber.objects.create(email='gone@example.com', is_active=False)
        self.age_cart()
        self.assertEqual(send_abandoned_cart_reminders(), 0)
