import os
import subprocess
import sys
from pathlib import Path

from django.contrib.auth.models import User
from django.template import Context, Template
from django.test import RequestFactory, TestCase, override_settings
from django.urls import path

from config.urls import urlpatterns as site_urlpatterns
from products.models import Category, Product

BASE_DIR = Path(__file__).resolve().parent.parent


def boom(request):
    raise RuntimeError('boom')


# Used by ErrorPageTests to trigger a real server error.
urlpatterns = [path('boom/', boom)] + site_urlpatterns


class LayoutTests(TestCase):
    """Every page must show the top bar and the sidebar."""

    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name='Phones')
        cls.product = Product.objects.create(
            category=cls.category, title='Test Phone', description='A phone', price=1000, stock=5,
        )
        cls.user = User.objects.create_user('u', 'u@example.com', 'Str0ng-pass!')

    def assertHasLayout(self, response):
        self.assertContains(response, 'class="app-topbar')
        self.assertContains(response, 'id="appSidebar"')

    def test_public_pages_have_topbar_and_sidebar(self):
        for url in ['/', '/shop/', self.category.get_absolute_url(), self.product.get_absolute_url(),
                    '/cart/', '/accounts/login/', '/accounts/signup/', '/accounts/password/reset/']:
            with self.subTest(url=url):
                self.assertHasLayout(self.client.get(url))

    def test_account_pages_have_topbar_and_sidebar(self):
        self.client.force_login(self.user)
        for url in ['/profile/', '/profile/wishlist/', '/orders/', '/profile/addresses/new/']:
            with self.subTest(url=url):
                self.assertHasLayout(self.client.get(url))

    def test_sidebar_lists_categories_and_marks_current_page(self):
        response = self.client.get(self.category.get_absolute_url())
        self.assertContains(response, f'sidebar-link active" href="{self.category.get_absolute_url()}"')

    def test_sidebar_shows_account_links_only_when_logged_in(self):
        self.assertNotContains(self.client.get('/'), 'Profile &amp; addresses')
        self.client.force_login(self.user)
        self.assertContains(self.client.get('/'), 'Profile &amp; addresses')


@override_settings(DEBUG=False)
class ErrorPageTests(TestCase):
    def test_404_uses_site_layout(self):
        response = self.client.get('/no-such-page/')
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'Page not found', status_code=404)
        self.assertContains(response, 'id="appSidebar"', status_code=404)

    @override_settings(ROOT_URLCONF='config.tests')
    def test_500_uses_site_layout(self):
        self.client.raise_request_exception = False
        response = self.client.get('/boom/')
        self.assertEqual(response.status_code, 500)
        self.assertContains(response, 'Something went wrong', status_code=500)
        self.assertContains(response, 'id="appSidebar"', status_code=500)


class NavActiveTagTests(TestCase):
    def render(self, path, url, exact=False):
        template = Template('{% load shop_tags %}{% nav_active url exact=exact %}')
        request = RequestFactory().get(path)
        return template.render(Context({'request': request, 'url': url, 'exact': exact}))

    def test_prefix_and_exact_matching(self):
        self.assertEqual(self.render('/orders/SCB-1/', '/orders/'), 'active')
        self.assertEqual(self.render('/shop/', '/', exact=True), '')
        self.assertEqual(self.render('/', '/', exact=True), 'active')

    def test_no_request_renders_nothing(self):
        template = Template('{% load shop_tags %}{% nav_active "/" %}')
        self.assertEqual(template.render(Context({})), '')


class SettingsTests(TestCase):
    """Run Django in a subprocess so each case gets freshly loaded settings."""

    def run_manage(self, *args, **env):
        full_env = {**os.environ, 'DEBUG': 'True', 'DATABASE_URL': '', **env}
        return subprocess.run(
            [sys.executable, 'manage.py', *args], cwd=BASE_DIR, env=full_env,
            capture_output=True, text=True, timeout=120,
        )

    def test_sqlite_database_url_works(self):
        result = self.run_manage('check', DATABASE_URL='sqlite:///:memory:')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_production_settings_pass_deploy_check(self):
        result = self.run_manage(
            'check', '--deploy',
            DEBUG='False', SECRET_KEY='x' * 30 + 'production-only-test-key-0123456789',
            ALLOWED_HOSTS='shop.example.com',
        )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        # HSTS subdomains/preload (W005, W021) are opt-in on purpose: they are hard to undo.
        for check_id in ['W004', 'W008', 'W009', 'W012', 'W016', 'W018', 'W020']:
            self.assertNotIn(f'security.{check_id}', output)

    def test_production_requires_secret_key(self):
        result = self.run_manage('check', DEBUG='False', SECRET_KEY='')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SECRET_KEY', result.stderr)
