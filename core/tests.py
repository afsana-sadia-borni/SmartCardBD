from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from products.models import Category, Product
from products.templatetags.shop_tags import lakh_group


class PwaTests(TestCase):
    def test_manifest(self):
        data = self.client.get(reverse('pwa_manifest')).json()
        self.assertEqual(data['display'], 'standalone')
        self.assertTrue(any(i.get('purpose') == 'maskable' for i in data['icons']))

    def test_service_worker_served_from_root_with_offline_fallback(self):
        response = self.client.get('/sw.js')
        self.assertEqual(response['Content-Type'], 'application/javascript')
        self.assertEqual(response['Service-Worker-Allowed'], '/')
        self.assertContains(response, reverse('offline'))

    def test_offline_and_credits_pages(self):
        self.assertContains(self.client.get(reverse('offline')), "You're offline")
        self.assertContains(self.client.get(reverse('image_credits')), 'Wikimedia Commons')


class SiteTests(TestCase):
    def test_admin_moved_off_default_url(self):
        self.assertEqual(self.client.get('/admin/').status_code, 404)
        self.assertEqual(self.client.get('/' + settings.ADMIN_URL).status_code, 302)
        self.assertContains(self.client.get('/robots.txt'), f'Disallow: /{settings.ADMIN_URL}')

    def test_bangla_digits_mode(self):
        category = Category.objects.create(name='Phones')
        Product.objects.create(category=category, title='Phone', price=125000, stock=3, description='x')
        self.assertContains(self.client.get('/shop/'), '৳1,25,000')
        self.client.cookies['digits'] = 'bn'
        self.assertContains(self.client.get('/shop/'), '৳১,২৫,০০০')

    def test_lakh_grouping(self):
        self.assertEqual([lakh_group(s) for s in ['999', '1000', '125000', '12500000']],
                         ['999', '1,000', '1,25,000', '1,25,00,000'])

    def test_whatsapp_button_only_when_configured(self):
        self.assertNotContains(self.client.get('/'), 'wa.me/88')
        with self.settings(WHATSAPP_NUMBER='8801712345678'):
            self.assertContains(self.client.get('/'), 'https://wa.me/8801712345678')

    def test_skip_link_and_layout_landmarks(self):
        response = self.client.get('/')
        self.assertContains(response, 'href="#main-content"')
        self.assertContains(response, 'id="miniCart"')
        self.assertContains(response, 'id="quickViewModal"')
