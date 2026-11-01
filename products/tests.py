from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from orders.models import Order, OrderItem

from .models import Category, Product, Review


def make_product(category=None, **kwargs):
    category = category or Category.objects.get_or_create(name='Phones')[0]
    defaults = {'title': 'Test Phone', 'price': Decimal('1000'), 'stock': 10, 'description': 'A phone'}
    defaults.update(kwargs)
    return Product.objects.create(category=category, **defaults)


class ProductModelTests(TestCase):
    def test_slugs_are_unique(self):
        a = make_product(title='Galaxy A15')
        b = make_product(title='Galaxy A15')
        self.assertEqual(a.slug, 'galaxy-a15')
        self.assertEqual(b.slug, 'galaxy-a15-2')

    def test_discount_price(self):
        p = make_product(price=Decimal('1000'), discount_price=Decimal('800'))
        self.assertTrue(p.has_discount)
        self.assertEqual(p.final_price, Decimal('800'))
        self.assertEqual(p.discount_percent, 20)

    def test_discount_higher_than_price_is_ignored(self):
        p = make_product(price=Decimal('1000'), discount_price=Decimal('1200'))
        self.assertFalse(p.has_discount)
        self.assertEqual(p.final_price, Decimal('1000'))


class ProductListTests(TestCase):
    def setUp(self):
        self.phones = Category.objects.create(name='Phones')
        self.laptops = Category.objects.create(name='Laptops')
        self.cheap = make_product(self.phones, title='Budget Phone', brand='Xiaomi', price=Decimal('500'))
        self.pricey = make_product(self.phones, title='Flagship Phone', brand='Samsung', price=Decimal('5000'),
                                   discount_price=Decimal('4000'))
        self.laptop = make_product(self.laptops, title='Office Laptop', price=Decimal('3000'), stock=0)
        self.hidden = make_product(self.phones, title='Hidden Phone', is_active=False)

    def titles(self, response):
        return [p.title for p in response.context['products']]

    def test_inactive_products_are_hidden(self):
        response = self.client.get(reverse('product_list'))
        self.assertNotIn('Hidden Phone', self.titles(response))
        self.assertEqual(self.client.get(self.hidden.get_absolute_url()).status_code, 404)

    def test_search(self):
        response = self.client.get(reverse('product_list'), {'q': 'samsung'})
        self.assertEqual(self.titles(response), ['Flagship Phone'])

    def test_category_page(self):
        response = self.client.get(reverse('category_detail', args=[self.laptops.slug]))
        self.assertEqual(self.titles(response), ['Office Laptop'])

    def test_price_filter_uses_sale_price(self):
        response = self.client.get(reverse('product_list'), {'min_price': 3500, 'max_price': 4500})
        self.assertEqual(self.titles(response), ['Flagship Phone'])

    def test_in_stock_filter(self):
        response = self.client.get(reverse('product_list'), {'in_stock': '1'})
        self.assertNotIn('Office Laptop', self.titles(response))

    def test_sort_by_price(self):
        response = self.client.get(reverse('product_list'), {'sort': 'price_asc'})
        self.assertEqual(self.titles(response), ['Budget Phone', 'Office Laptop', 'Flagship Phone'])

    def test_home_shows_newest_featured_first(self):
        old = make_product(self.phones, title='Old Featured', is_featured=True)
        new = make_product(self.phones, title='New Featured', is_featured=True)
        response = self.client.get(reverse('home'))
        self.assertEqual(list(response.context['featured_products']), [new, old])

    def test_bad_params_are_ignored(self):
        response = self.client.get(reverse('product_list'), {'sort': 'nope', 'min_price': 'abc', 'page': 'x'})
        self.assertEqual(response.status_code, 200)

    def test_old_id_url_redirects_to_slug(self):
        response = self.client.get(f'/product/{self.cheap.id}/')
        self.assertRedirects(response, self.cheap.get_absolute_url(), status_code=301)


class ReviewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('buyer', 'buyer@example.com', 'pass12345!')
        self.product = make_product()
        self.client.force_login(self.user)
        self.url = reverse('add_review', args=[self.product.slug])

    def _order(self, status):
        order = Order.objects.create(
            user=self.user, full_name='B', email='b@example.com', phone='01712345678', district='Dhaka',
            area='Mirpur', address_line='1', subtotal=1000, shipping_cost=60, total=1060, status=status,
        )
        OrderItem.objects.create(order=order, product=self.product, product_title='x', price=1000, quantity=1)

    def test_cannot_review_without_delivered_order(self):
        self._order(Order.Status.SHIPPED)
        self.client.post(self.url, {'rating': 5, 'comment': 'Great'})
        self.assertFalse(Review.objects.exists())

    def test_review_after_delivery_and_update(self):
        self._order(Order.Status.DELIVERED)
        self.client.post(self.url, {'rating': 4, 'comment': 'Good'})
        self.client.post(self.url, {'rating': 2, 'comment': 'Changed my mind'})
        review = Review.objects.get()
        self.assertEqual(review.rating, 2)

        response = self.client.get(self.product.get_absolute_url())
        self.assertEqual(response.context['product'].avg_rating, 2)
