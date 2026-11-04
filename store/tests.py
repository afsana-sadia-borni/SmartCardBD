from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts.models import Notification
from orders.models import Coupon, Order, OrderItem, ReturnRequest
from products.models import Category, FlashSale, Product, ProductVariant, Question

SHIPPING = dict(full_name='Rahim Uddin', email='rahim@example.com', phone='01712345678', district='Dhaka',
                upazila='Mirpur (Dhaka City)', area='Mirpur', address_line='House 1')


class StoreTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user('owner', 'owner@example.com', 'Str0ng-pass!', is_staff=True,
                                              is_superuser=True)
        self.customer = User.objects.create_user('cust', 'cust@example.com', 'Str0ng-pass!')
        self.category = Category.objects.create(name='Audio')
        self.product = Product.objects.create(category=self.category, title='Speaker', price=Decimal('1500'),
                                              stock=10, description='x')

    def make_order(self, **extra):
        order = Order.objects.create(user=self.customer, subtotal=Decimal('1500'), shipping_cost=Decimal('60'),
                                     total=Decimal('1560'), **{**SHIPPING, **extra})
        OrderItem.objects.create(order=order, product=self.product, product_title='Speaker', price=Decimal('1500'),
                                 quantity=1)
        return order

    def staff_with_role(self, role):
        user = User.objects.create_user(role, f'{role.split()[0].lower()}@example.com', 'Str0ng-pass!', is_staff=True)
        user.groups.add(Group.objects.get(name=role))
        return user


class AccessTests(StoreTestCase):
    def test_login_and_staff_required(self):
        url = reverse('store:dashboard')
        # Visitors and customers can't even tell the panel exists.
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(reverse('store:orders')).status_code, 404)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(reverse('store:team'), {'email': 'cust@example.com'}).status_code, 404)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(url), 'Store dashboard')

    def test_roles_limit_sections_and_menu(self):
        self.client.force_login(self.staff_with_role('Order manager'))
        page = self.client.get(reverse('store:dashboard'))
        self.assertContains(page, reverse('store:orders'))
        self.assertNotContains(page, reverse('store:coupons'))
        self.assertEqual(self.client.get(reverse('store:orders')).status_code, 200)
        self.assertEqual(self.client.get(reverse('store:products')).status_code, 403)
        self.assertEqual(self.client.get(reverse('store:team')).status_code, 403)

        self.client.force_login(self.staff_with_role('Catalog manager'))
        self.assertEqual(self.client.get(reverse('store:products')).status_code, 200)
        self.assertEqual(self.client.get(reverse('store:orders')).status_code, 403)

    def test_staff_login_lands_in_store_and_shop_shows_store_button(self):
        response = self.client.post(reverse('account_login'), {'login': 'owner@example.com', 'password': 'Str0ng-pass!'})
        self.assertRedirects(response, reverse('store:dashboard'), fetch_redirect_response=False)
        self.assertContains(self.client.get('/'), 'Store panel')
        self.client.logout()
        response = self.client.post(reverse('account_login'), {'login': 'cust@example.com', 'password': 'Str0ng-pass!'})
        self.assertRedirects(response, reverse('home'), fetch_redirect_response=False)
        self.assertNotContains(self.client.get('/'), 'Store panel')

    def test_old_dashboard_url_redirects(self):
        self.client.force_login(self.owner)
        self.assertRedirects(self.client.get('/dashboard/'), reverse('store:dashboard'))
        self.assertContains(self.client.get(reverse('admin:index')), reverse('store:dashboard'))


class OrderTests(StoreTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.owner)

    def act(self, order, action):
        return self.client.post(reverse('store:order_action', args=[order.order_number]), {'action': action})

    def test_tabs_search_and_detail(self):
        order = self.make_order()
        self.make_order(full_name='Karim', phone='01811111111', status=Order.Status.SHIPPED)
        listing = self.client.get(reverse('store:orders'), {'status': 'pending'})
        self.assertContains(listing, order.order_number)
        self.assertNotContains(listing, 'Karim')
        self.assertContains(self.client.get(reverse('store:orders'), {'q': '01811111111'}), 'Karim')
        detail = self.client.get(reverse('store:order_detail', args=[order.order_number]))
        self.assertContains(detail, 'Confirm order')
        self.assertContains(detail, 'tel:01712345678')

    def test_confirm_ship_deliver_notifies_and_marks_cod_paid(self):
        order = self.make_order()
        with self.captureOnCommitCallbacks(execute=True):
            for action in ('confirm', 'ship', 'deliver'):
                self.act(order, action)
        order.refresh_from_db()
        self.assertEqual((order.status, order.payment_status), ('delivered', 'paid'))
        messages = list(Notification.objects.filter(user=self.customer).values_list('message', flat=True))
        for word in ('confirmed', 'shipped', 'delivered', 'points'):
            self.assertTrue(any(word in m for m in messages), word)
        timeline = self.client.get(reverse('store:order_detail', args=[order.order_number])).context['timeline']
        self.assertEqual([status for _, status, _ in timeline], ['Pending', 'Confirmed', 'Shipped', 'Delivered'])

    def test_actions_out_of_order_are_refused(self):
        order = self.make_order()
        self.act(order, 'deliver')
        order.refresh_from_db()
        self.assertEqual(order.status, 'pending')

    def test_cancel_restocks(self):
        order = self.make_order()
        self.act(order, 'cancel')
        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual((order.status, self.product.stock), ('cancelled', 11))


class CatalogTests(StoreTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.owner)

    def photo(self):
        buffer = BytesIO()
        Image.new('RGB', (40, 40), 'red').save(buffer, 'JPEG')
        return SimpleUploadedFile('p.jpg', buffer.getvalue(), content_type='image/jpeg')

    def product_post(self, **extra):
        data = {
            'title': 'Headphones', 'category': self.category.pk, 'brand': 'Sony', 'description': 'Nice',
            'price': '5000', 'discount_price': '', 'stock': '3', 'is_active': 'on',
            'variants-TOTAL_FORMS': '1', 'variants-INITIAL_FORMS': '0',
            'variants-0-color': 'Black', 'variants-0-stock': '7', 'variants-0-is_active': 'on',
            'gallery-TOTAL_FORMS': '0', 'gallery-INITIAL_FORMS': '0',
        }
        data.update(extra)
        return self.client.post(reverse('store:product_add'), data)

    def test_add_product_with_option(self):
        response = self.product_post()
        product = Product.objects.get(title='Headphones')
        self.assertRedirects(response, reverse('store:product_edit', args=[product.pk]))
        self.assertEqual(product.variants.get().color, 'Black')
        product.refresh_from_db()
        self.assertEqual(product.stock, 7)  # options' stock is added up
        self.assertEqual(self.client.get(reverse('store:product_edit', args=[product.pk])).status_code, 200)

    @override_settings(MEDIA_ROOT='/tmp/scb-store-test-media')
    def test_add_product_with_photo(self):
        self.product_post(image=self.photo(), **{'variants-TOTAL_FORMS': '0'})
        self.assertTrue(Product.objects.get(title='Headphones').image)

    def test_sale_price_must_be_lower(self):
        response = self.product_post(discount_price='6000')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(title='Headphones').exists())

    def test_quick_stock_and_visibility(self):
        url = reverse('store:product_quick_update', args=[self.product.pk])
        self.client.post(url, {'stock': '25'})
        self.client.post(url, {'toggle_active': '1'})
        self.product.refresh_from_db()
        self.assertEqual((self.product.stock, self.product.is_active), (25, False))
        self.client.post(url, {'stock': '-1'})
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 25)
        ProductVariant.objects.create(product=self.product, color='Red', stock=4)
        self.client.post(url, {'stock': '99'})
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 4)
        self.assertContains(self.client.get(reverse('store:products'), {'stock': 'low'}), 'Speaker')

    def test_next_url_must_stay_on_this_site(self):
        url = reverse('store:product_quick_update', args=[self.product.pk])
        response = self.client.post(url, {'stock': '5', 'next': 'https://evil.example/phish'})
        self.assertRedirects(response, reverse('store:products'), fetch_redirect_response=False)
        response = self.client.post(url, {'stock': '6', 'next': '/store/products/?stock=low'})
        self.assertRedirects(response, '/store/products/?stock=low', fetch_redirect_response=False)

    def test_coupon_and_flash_sale_forms(self):
        now = timezone.localtime()
        fmt = '%Y-%m-%dT%H:%M'
        self.client.post(reverse('store:coupon_add'), {
            'code': 'eid50', 'discount_type': 'flat', 'value': '50', 'min_order_amount': '0',
            'valid_from': now.strftime(fmt), 'valid_to': (now + timedelta(days=3)).strftime(fmt), 'is_active': 'on',
        })
        self.assertTrue(Coupon.objects.filter(code='EID50').exists())
        self.assertContains(self.client.get(reverse('store:coupons')), 'EID50')
        self.client.post(reverse('store:flash_sale_add'), {
            'title': 'Weekend', 'discount_percent': '20', 'starts_at': now.strftime(fmt),
            'ends_at': (now + timedelta(hours=5)).strftime(fmt), 'products': [self.product.pk], 'is_active': 'on',
        })
        sale = FlashSale.objects.get()
        self.assertEqual(list(sale.products.all()), [self.product])
        self.assertContains(self.client.get(reverse('store:flash_sales')), 'Running')

    def test_other_sections_render(self):
        for name in ('banners', 'delivery', 'customers', 'team', 'banner_add', 'delivery_add'):
            self.assertEqual(self.client.get(reverse(f'store:{name}')).status_code, 200, name)


class SupportTests(StoreTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.owner)

    def test_return_decision_notifies_customer(self):
        order = self.make_order(status=Order.Status.DELIVERED)
        rr = ReturnRequest.objects.create(order=order, reason='damaged', details='Broken')
        self.assertContains(self.client.get(reverse('store:returns')), 'Broken')
        self.client.post(reverse('store:return_decide', args=[rr.pk]), {'status': 'approved', 'admin_note': 'Pickup tomorrow'})
        rr.refresh_from_db()
        self.assertEqual((rr.status, rr.admin_note), ('approved', 'Pickup tomorrow'))
        self.assertTrue(Notification.objects.filter(user=self.customer, message__contains='Approved').exists())

    def test_answer_question(self):
        q = Question.objects.create(product=self.product, user=self.customer, question='Is it waterproof?')
        self.assertContains(self.client.get(reverse('store:questions')), 'waterproof')
        self.client.post(reverse('store:question_answer', args=[q.pk]), {'answer': 'Yes, IPX5.'})
        q.refresh_from_db()
        self.assertEqual((q.answer, q.answered_by), ('Yes, IPX5.', self.owner))
        self.assertTrue(Notification.objects.filter(user=self.customer, message__contains='answered').exists())


class TeamTests(StoreTestCase):
    def test_owner_adds_and_removes_staff(self):
        self.client.force_login(self.owner)
        self.client.post(reverse('store:team'), {'email': 'cust@example.com', 'role': 'Order manager'})
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_staff)
        self.assertTrue(self.customer.has_perm('orders.change_order'))
        self.client.post(reverse('store:team_remove', args=[self.customer.pk]))
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_staff)
        self.assertFalse(self.customer.groups.exists())

    def test_unknown_email_is_rejected(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse('store:team'), {'email': 'nobody@example.com', 'role': 'Order manager'})
        self.assertContains(response, 'No account with this email')


class CatalogCsvTests(StoreTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.owner)

    def upload(self, text, dry_run=False):
        from django.core.files.uploadedfile import SimpleUploadedFile
        data = {'file': SimpleUploadedFile('p.csv', text.encode('utf-8-sig'), content_type='text/csv')}
        if dry_run:
            data['dry_run'] = '1'
        return self.client.post(reverse('store:products_import'), data, follow=True)

    def test_export_then_import_updates_and_creates(self):
        exported = self.client.get(reverse('store:products_export')).content.decode('utf-8-sig')
        self.assertIn('speaker', exported)
        csv_text = ('slug,title,category,brand,price,sale_price,stock,is_active\n'
                    f'{self.product.slug},Speaker Pro,Audio,JBL,"1,800",1600,7,yes\n'
                    ',Earbuds,Earphones,QCY,2200,,30,yes\n')
        self.upload(csv_text, dry_run=True)
        self.assertFalse(Product.objects.filter(title='Earbuds').exists())  # check-only saves nothing
        self.upload(csv_text)
        self.product.refresh_from_db()
        self.assertEqual((self.product.title, self.product.price, self.product.discount_price, self.product.stock),
                         ('Speaker Pro', Decimal('1800'), Decimal('1600'), 7))
        self.assertEqual(Product.objects.get(title='Earbuds').category.name, 'Earphones')

    def test_one_bad_row_saves_nothing(self):
        response = self.upload('title,category,price,stock\nGood,Audio,100,1\nBad,Audio,abc,1\nWorse,Audio,50,-2\n')
        self.assertContains(response, 'Nothing was saved')
        self.assertContains(response, 'is not a number')
        self.assertFalse(Product.objects.filter(title='Good').exists())

    def test_missing_columns(self):
        self.assertContains(self.upload('name,cost\nA,1\n'), 'Missing column')


class ReportTests(StoreTestCase):
    def test_reports_for_ranges(self):
        self.make_order()
        self.make_order(status=Order.Status.CANCELLED)
        self.client.force_login(self.owner)
        page = self.client.get(reverse('store:reports'), {'days': '7'})
        self.assertEqual(page.context['order_count'], 1)
        self.assertEqual(page.context['cancel_rate'], 50.0)
        self.assertIn('Cash on Delivery', page.context['charts'])
        custom = self.client.get(reverse('store:reports'), {'from': '2020-01-01', 'to': '2020-01-31'})
        self.assertEqual(custom.context['order_count'], 0)
        self.assertEqual(self.client.get(reverse('store:reports'), {'from': 'bad'}).status_code, 200)

    def test_catalog_manager_cannot_see_reports(self):
        self.client.force_login(self.staff_with_role('Catalog manager'))
        self.assertEqual(self.client.get(reverse('store:reports')).status_code, 403)


class IntegrationsTests(StoreTestCase):
    def test_owner_sees_status_and_can_send_tests(self):
        from django.core import mail

        self.client.force_login(self.owner)
        page = self.client.get(reverse('store:integrations'))
        self.assertContains(page, 'Courier (Steadfast)')
        self.assertContains(page, 'Not set up')
        self.client.post(reverse('store:integrations'), {'test': 'email'})
        self.assertEqual(mail.outbox[-1].to, ['owner@example.com'])
        response = self.client.post(reverse('store:integrations'), {'test': 'sms', 'phone': '01712345678'}, follow=True)
        self.assertContains(response, 'written to the log')

    def test_staff_cannot_open_it(self):
        self.client.force_login(self.staff_with_role('Order manager'))
        self.assertEqual(self.client.get(reverse('store:integrations')).status_code, 403)
