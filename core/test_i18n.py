from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from products.models import Category, Product


class BanglaTests(TestCase):
    def setUp(self):
        Product.objects.create(category=Category.objects.create(name='Audio'), title='Speaker',
                               price=Decimal('125000'), stock=5, description='x')

    def switch(self, language):
        return self.client.post(reverse('set_language'), {'language': language, 'next': '/shop/'})

    def test_english_by_default_with_a_bangla_button(self):
        page = self.client.get('/shop/')
        self.assertContains(page, '<html lang="en"')
        self.assertContains(page, 'Add to cart')
        self.assertContains(page, 'বাংলা')  # the switch

    def test_switching_to_bangla_translates_the_shop_and_digits(self):
        self.assertRedirects(self.switch('bn'), '/shop/', fetch_redirect_response=False)
        page = self.client.get('/shop/')
        self.assertContains(page, '<html lang="bn"')
        self.assertContains(page, 'কার্টে যোগ করুন')
        self.assertContains(page, '৳১,২৫,০০০')
        self.assertContains(page, 'Hind+Siliguri')
        self.switch('en')
        self.assertContains(self.client.get('/shop/'), 'Add to cart')

    def test_messages_forms_and_policies_in_bangla(self):
        self.switch('bn')
        self.assertContains(self.client.get(reverse('checkout'), follow=True), 'আপনার কার্ট খালি।')
        self.assertContains(self.client.get(reverse('account_signup')), 'মোবাইল নম্বর')
        self.assertContains(self.client.get(reverse('policy_page', args=['returns'])), 'রিফান্ড')

    def test_javascript_strings(self):
        self.switch('bn')
        # The catalog is JSON, so Bangla arrives \u-escaped.
        self.assertContains(self.client.get(reverse('javascript-catalog')), 'স্টকে মাত্র'.encode('unicode_escape').decode())

    def test_store_panel_stays_in_english(self):
        owner = User.objects.create_user('o', 'o@example.com', 'x', is_staff=True, is_superuser=True)
        self.switch('bn')
        self.client.force_login(owner)
        page = self.client.get(reverse('store:dashboard'))
        self.assertContains(page, 'Store dashboard')
        self.assertContains(page, '<html lang="en"')
