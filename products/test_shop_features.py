import io
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts.models import Notification
from orders.models import Order, OrderItem
from orders.services import cancel_order

from .admin import QuestionAdmin
from .models import Bundle, Category, FlashSale, PriceAlert, Product, ProductVariant, Question, Review

AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
SHIPPING = {
    'full_name': 'Rahim Uddin', 'email': 'rahim@example.com', 'phone': '01712345678', 'district': 'Dhaka',
    'upazila': 'Mirpur (Dhaka City)', 'area': 'Mirpur', 'address_line': 'House 1', 'payment_method': 'cod',
}


def make_image(name='photo.jpg'):
    buf = io.BytesIO()
    Image.new('RGB', (20, 20), 'orange').save(buf, 'JPEG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/jpeg')


class ShopTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.category = Category.objects.create(name='Fashion')
        self.shirt = Product.objects.create(category=self.category, title='Polo Shirt', price=Decimal('1000'),
                                            stock=0, description='Cotton polo')
        self.red_m = ProductVariant.objects.create(product=self.shirt, color='Red', size='M', stock=3)
        self.red_l = ProductVariant.objects.create(product=self.shirt, color='Red', size='L', stock=1,
                                                   price=Decimal('1200'))
        self.mouse = Product.objects.create(category=self.category, title='Silent Mouse', price=Decimal('500'),
                                            stock=10, description='Quiet mouse')

    def add(self, product, qty=1, variant=None, ajax=False):
        data = {'product_id': product.id, 'quantity': qty}
        if variant:
            data['variant_id'] = variant.id
        return self.client.post(reverse('cart_add'), data, **(AJAX if ajax else {}))


class VariantTests(ShopTestCase):
    def test_product_stock_is_total_of_variants(self):
        self.shirt.refresh_from_db()
        self.assertEqual(self.shirt.stock, 4)

    def test_variant_required_for_products_with_options(self):
        response = self.add(self.shirt, ajax=True)
        self.assertTrue(response.json()['needs_options'])
        self.assertEqual(response.json()['cart_count'], 0)

    def test_variant_quantity_capped_at_variant_stock_and_uses_variant_price(self):
        data = self.add(self.shirt, 5, self.red_l, ajax=True).json()
        self.assertEqual(data['cart_count'], 1)
        self.assertEqual(Decimal(data['subtotal']), Decimal('1200'))
        self.assertIn('mini_cart_html', data)

    def test_order_decrements_and_cancel_restores_variant_stock(self):
        self.add(self.shirt, 2, self.red_m)
        self.client.post(reverse('checkout'), SHIPPING)
        order = Order.objects.get()
        item = order.items.get()
        self.assertEqual((item.variant, item.variant_label), (self.red_m, 'Red / M'))
        self.red_m.refresh_from_db()
        self.shirt.refresh_from_db()
        self.assertEqual((self.red_m.stock, self.shirt.stock), (1, 2))
        cancel_order(order)
        self.red_m.refresh_from_db()
        self.shirt.refresh_from_db()
        self.assertEqual((self.red_m.stock, self.shirt.stock), (3, 4))

    def test_detail_page_offers_options(self):
        response = self.client.get(self.shirt.get_absolute_url())
        self.assertContains(response, 'data-variants=')
        self.assertContains(response, 'name="opt_size"')


class FlashSaleTests(ShopTestCase):
    def test_running_sale_lowers_price_and_ends_automatically(self):
        sale = FlashSale.objects.create(discount_percent=20, ends_at=timezone.now() + timedelta(hours=2))
        sale.products.add(self.mouse)
        mouse = Product.objects.get(pk=self.mouse.pk)
        self.assertEqual(mouse.final_price, Decimal('400.00'))
        self.assertEqual(mouse.discount_percent, 20)
        self.assertContains(self.client.get('/'), 'js-countdown')

        FlashSale.objects.filter(pk=sale.pk).update(ends_at=timezone.now() - timedelta(seconds=1))
        cache.clear()
        self.assertEqual(Product.objects.get(pk=self.mouse.pk).final_price, Decimal('500'))

    def test_sale_price_wins_when_lower_than_flash_price(self):
        self.mouse.discount_price = Decimal('350')
        self.mouse.save()
        sale = FlashSale.objects.create(discount_percent=10, ends_at=timezone.now() + timedelta(hours=1))
        sale.products.add(self.mouse)
        self.assertEqual(Product.objects.get(pk=self.mouse.pk).final_price, Decimal('350'))


class BundleTests(ShopTestCase):
    def test_bundle_discount_applies_in_cart_and_order(self):
        plain = Product.objects.create(category=self.category, title='Pad', price=Decimal('300'), stock=5,
                                       description='x')
        bundle = Bundle.objects.create(title='Mouse + pad', bundle_price=Decimal('700'))
        bundle.products.set([self.mouse, plain])
        self.add(self.mouse, 2)
        data = self.add(plain, 1, ajax=True).json()
        self.assertEqual(Decimal(data['bundle_discount']), Decimal('100'))  # one complete set
        self.client.post(reverse('checkout'), SHIPPING)
        order = Order.objects.get()
        self.assertEqual(order.bundle_discount, Decimal('100'))
        self.assertEqual(order.total, Decimal('1300') - Decimal('100') + order.shipping_cost)


class SearchAndBrowseTests(ShopTestCase):
    def test_search_suggest_returns_top_matches(self):
        data = self.client.get(reverse('search_suggest'), {'q': 'sil'}).json()
        self.assertEqual([r['title'] for r in data['results']], ['Silent Mouse'])
        self.assertEqual(data['results'][0]['price'], '৳500')
        self.assertEqual(self.client.get(reverse('search_suggest'), {'q': 's'}).json()['results'], [])

    def test_quick_view_partial(self):
        response = self.client.get(reverse('quick_view', args=[self.mouse.slug]))
        self.assertContains(response, 'Silent Mouse')
        self.assertNotContains(response, '<html')

    def test_infinite_scroll_returns_next_page_of_cards(self):
        for i in range(14):
            Product.objects.create(category=self.category, title=f'Item {i}', price=100, stock=1, description='x')
        data = self.client.get(reverse('product_list'), {'partial': 1}).json()
        self.assertEqual(data['html'].count('product-card'), 12)
        self.assertIn('page=2', data['next_url'])
        last = self.client.get(reverse('product_list'), {'partial': 1, 'page': 2}).json()
        self.assertIsNone(last['next_url'])

    def test_compare_keeps_at_most_four(self):
        products = [Product.objects.create(category=self.category, title=f'C{i}', price=1, stock=1, description='x')
                    for i in range(5)]
        for p in products:
            data = self.client.post(reverse('compare_toggle', args=[p.id]), **AJAX).json()
        self.assertEqual(data['count'], 4)
        self.assertNotIn(products[0].id, self.client.session['compare'])
        self.assertContains(self.client.get(reverse('compare')), 'C4')

    def test_sold_count_uses_real_orders(self):
        order = Order.objects.create(full_name='a', email='a@a.com', phone='01712345678', district='Dhaka',
                                     area='x', address_line='x', subtotal=0, shipping_cost=0, total=0)
        OrderItem.objects.create(order=order, product=self.mouse, product_title='m', price=1, quantity=12)
        self.assertContains(self.client.get(self.mouse.get_absolute_url()), '10+ sold')


class PriceAlertTests(ShopTestCase):
    def test_customer_notified_when_price_drops(self):
        user = User.objects.create_user('u', 'u@example.com', 'pw-Str0ng!')
        self.client.force_login(user)
        data = self.client.post(reverse('price_alert_toggle', args=[self.mouse.id]), **AJAX).json()
        self.assertTrue(data['active'])
        with self.captureOnCommitCallbacks(execute=True):
            self.mouse.discount_price = Decimal('450')
            self.mouse.save()
        self.assertTrue(Notification.objects.filter(user=user, message__startswith='Price drop!').exists())
        self.assertIsNotNone(PriceAlert.objects.get().notified_at)


class QuestionAndReviewTests(ShopTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('q', 'q@example.com', 'pw-Str0ng!')
        self.client.force_login(self.user)

    def test_ask_and_answer_notifies_customer(self):
        self.client.post(reverse('ask_question', args=[self.mouse.slug]), {'question': 'Does it have a warranty?'})
        question = Question.objects.get()
        staff = User.objects.create_user('s', 's@example.com', 'x', is_staff=True)

        class Form:
            changed_data = ['answer']

        request = type('R', (), {'user': staff})()
        question.answer = 'Yes, 1 year.'
        QuestionAdmin(Question, None).save_model(request, question, Form(), True)
        self.assertTrue(Notification.objects.filter(user=self.user, message__contains='answered').exists())
        self.assertContains(self.client.get(self.mouse.get_absolute_url()), 'Yes, 1 year.')

    def test_review_with_photos(self):
        order = Order.objects.create(user=self.user, full_name='a', email='a@a.com', phone='01712345678',
                                     district='Dhaka', area='x', address_line='x', subtotal=0, shipping_cost=0,
                                     total=0, status=Order.Status.DELIVERED)
        OrderItem.objects.create(order=order, product=self.mouse, product_title='m', price=1, quantity=1)
        self.client.post(reverse('add_review', args=[self.mouse.slug]),
                         {'rating': 5, 'comment': 'Great', 'photos': [make_image('a.jpg'), make_image('b.jpg')]})
        self.assertEqual(Review.objects.get().images.count(), 2)

    def test_review_rejects_non_images(self):
        order = Order.objects.create(user=self.user, full_name='a', email='a@a.com', phone='01712345678',
                                     district='Dhaka', area='x', address_line='x', subtotal=0, shipping_cost=0,
                                     total=0, status=Order.Status.DELIVERED)
        OrderItem.objects.create(order=order, product=self.mouse, product_title='m', price=1, quantity=1)
        bad = SimpleUploadedFile('x.jpg', b'not an image', content_type='image/jpeg')
        self.client.post(reverse('add_review', args=[self.mouse.slug]), {'rating': 5, 'photos': [bad]})
        self.assertFalse(Review.objects.exists())
