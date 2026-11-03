from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from products.models import Category, Product

from .models import Address, Wishlist

ADDRESS = {'full_name': 'Karim', 'phone': '01812345678', 'district': 'Sylhet', 'upazila': 'Balaganj', 'area': 'Zindabazar',
           'address_line': 'House 5'}


class AuthTests(TestCase):
    def test_signup_with_email(self):
        response = self.client.post(reverse('account_signup'), {
            'full_name': 'Nusrat Jahan', 'phone': '01712345678', 'email': 'new@example.com',
            'password1': 'Str0ng-pass!', 'password2': 'Str0ng-pass!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(get_user_model().objects.filter(email='new@example.com').exists())

    def test_cart_survives_login(self):
        product = Product.objects.create(category=Category.objects.create(name='C'), title='P',
                                         price=Decimal('10'), stock=5, description='x')
        self.client.post(reverse('cart_add'), {'product_id': product.id, 'quantity': 2})
        get_user_model().objects.create_user('u', 'u@example.com', 'Str0ng-pass!')
        self.client.post(reverse('account_login'), {'login': 'u@example.com', 'password': 'Str0ng-pass!'})
        self.assertEqual(len(self.client.get(reverse('cart_summary')).context['cart']), 2)


class AddressTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('u', 'u@example.com', 'pass12345!')
        self.client.force_login(self.user)

    def test_first_address_is_default_and_only_one_default(self):
        self.client.post(reverse('address_add'), ADDRESS)
        self.client.post(reverse('address_add'), {**ADDRESS, 'area': 'Amberkhana', 'is_default': 'on'})
        self.assertEqual(Address.objects.filter(user=self.user, is_default=True).count(), 1)
        self.assertEqual(Address.objects.get(is_default=True).area, 'Amberkhana')

    def test_deleting_default_promotes_another(self):
        first = Address.objects.create(user=self.user, **ADDRESS)
        second = Address.objects.create(user=self.user, **{**ADDRESS, 'area': 'Other'})
        self.client.post(reverse('address_delete', args=[first.pk]))
        second.refresh_from_db()
        self.assertTrue(second.is_default)

    def test_cannot_edit_someone_elses_address(self):
        other = get_user_model().objects.create_user('o', 'o@example.com', 'pass12345!')
        address = Address.objects.create(user=other, **ADDRESS)
        self.assertEqual(self.client.get(reverse('address_edit', args=[address.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('address_delete', args=[address.pk])).status_code, 404)


class WishlistTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(category=Category.objects.create(name='C'), title='P',
                                              price=Decimal('10'), stock=5, description='x')
        self.url = reverse('wishlist_toggle', args=[self.product.id])

    def test_requires_login(self):
        response = self.client.post(self.url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 401)

    def test_toggle(self):
        user = get_user_model().objects.create_user('u', 'u@example.com', 'pass12345!')
        self.client.force_login(user)
        data = self.client.post(self.url, HTTP_X_REQUESTED_WITH='XMLHttpRequest').json()
        self.assertTrue(data['in_wishlist'])
        self.assertContains(self.client.get(reverse('wishlist')), 'P')
        data = self.client.post(self.url, HTTP_X_REQUESTED_WITH='XMLHttpRequest').json()
        self.assertFalse(data['in_wishlist'])
        self.assertFalse(Wishlist.objects.exists())
