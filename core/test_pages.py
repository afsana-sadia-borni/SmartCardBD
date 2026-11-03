from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from products.management.commands.seed_demo import Command as SeedDemo
from products.models import Category, Product


class PolicyPageTests(TestCase):
    def test_pages_and_footer_links(self):
        for slug in ['about', 'shipping', 'returns', 'privacy', 'terms']:
            response = self.client.get(reverse('policy_page', args=[slug]))
            self.assertEqual(response.status_code, 200, slug)
            self.assertContains(response, 'id="miniCart"')  # inside the normal layout
        self.assertContains(self.client.get(reverse('policy_page', args=['shipping'])), 'Inside Dhaka')
        self.assertContains(self.client.get('/'), reverse('policy_page', args=['privacy']))
        self.assertEqual(self.client.get('/pages/nope/').status_code, 404)

    @override_settings(SUPPORT_EMAIL='help@example.com')
    def test_contact_details_from_settings(self):
        self.assertContains(self.client.get(reverse('policy_page', args=['about'])), 'help@example.com')


class DemoAccountTests(TestCase):
    def setUp(self):
        Product.objects.create(category=Category.objects.create(name='Audio'), title='Speaker',
                               price=Decimal('2500'), stock=5, description='x')

    def test_seed_creates_working_demo_account(self):
        with self.captureOnCommitCallbacks(execute=True):
            user = SeedDemo().add_demo_account()
            SeedDemo().add_demo_account()  # running seed_demo again is safe
        self.assertEqual(User.objects.filter(email=settings.DEMO_EMAIL).count(), 1)
        self.assertEqual(user.orders.get().status, 'delivered')
        user.profile.refresh_from_db()
        self.assertGreaterEqual(user.profile.points, 200)
        response = self.client.post(reverse('account_login'), {'login': settings.DEMO_EMAIL,
                                                               'password': settings.DEMO_PASSWORD})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    @override_settings(SHOW_DEMO_LOGIN=True)
    def test_login_page_shows_demo_box(self):
        self.assertContains(self.client.get(reverse('account_login')), 'js-demo-login')
        self.assertNotContains(self.client.get(reverse('account_signup')), 'js-demo-login')

    @override_settings(SHOW_DEMO_LOGIN=False)
    def test_demo_box_can_be_hidden(self):
        self.assertNotContains(self.client.get(reverse('account_login')), 'js-demo-login')

    def test_demo_password_cannot_be_changed(self):
        user = SeedDemo().add_demo_account()
        self.client.force_login(user)
        self.client.post(reverse('account_change_password'), {
            'oldpassword': settings.DEMO_PASSWORD, 'password1': 'Another-pass-123', 'password2': 'Another-pass-123',
        })
        user.refresh_from_db()
        self.assertTrue(user.check_password(settings.DEMO_PASSWORD))
