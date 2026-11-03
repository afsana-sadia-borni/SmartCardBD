from decimal import Decimal

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from products.models import Category, Product

from .invoice import bdt
from .models import Order

SHIPPING = {
    'full_name': 'Rahim Uddin', 'email': 'rahim@example.com', 'phone': '01712345678', 'district': 'Dhaka',
    'upazila': 'Mirpur (Dhaka City)', 'area': 'Mirpur', 'address_line': 'House 1', 'payment_method': 'cod',
}


class InvoiceTests(TestCase):
    def setUp(self):
        cache.clear()
        category = Category.objects.create(name='Gadgets')
        self.product = Product.objects.create(category=category, title='Speaker', price=Decimal('125000'), stock=10,
                                              description='x')
        self.user = User.objects.create_user('buyer', 'buyer@example.com', 'x')
        self.client.force_login(self.user)
        self.client.post(reverse('cart_add'), {'product_id': self.product.id, 'quantity': 1})
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('checkout'), SHIPPING)
        self.order = Order.objects.get()

    def test_confirmation_email_has_pdf_invoice(self):
        message = mail.outbox[-1]
        name, content, mimetype = message.attachments[0]
        self.assertEqual((name, mimetype), (f'invoice-{self.order.order_number}.pdf', 'application/pdf'))
        self.assertTrue(content.startswith(b'%PDF'))
        self.assertIn(f'http://localhost:8000{self.order.get_absolute_url()}', message.body)

    def test_owner_can_download_others_cannot(self):
        url = reverse('order_invoice', args=[self.order.order_number])
        response = self.client.get(url)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))
        self.client.force_login(User.objects.create_user('other', 'other@example.com', 'x'))
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_amounts_use_lakh_grouping(self):
        self.assertEqual(bdt(Decimal('125000')), 'BDT 1,25,000.00')
        self.assertEqual(bdt(Decimal('-99.5')), '-BDT 99.50')
