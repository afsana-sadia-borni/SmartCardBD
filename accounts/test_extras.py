from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from .models import CustomerProfile, Notification, Subscriber

AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}


class SignupTests(TestCase):
    def signup(self, email='new@example.com', phone='01712345678', **extra):
        return self.client.post(reverse('account_signup'), {
            'full_name': 'Nusrat Jahan', 'phone': phone, 'email': email,
            'password1': 'Str0ng-pass!', 'password2': 'Str0ng-pass!', **extra,
        })

    def test_new_user_gets_profile_and_referrer_from_link(self):
        friend = User.objects.create_user('friend', 'friend@example.com', 'x')
        code = friend.profile.referral_code
        self.client.get('/?ref=' + code)
        self.signup()
        profile = CustomerProfile.objects.get(user__email='new@example.com')
        self.assertEqual(profile.referred_by, friend)
        self.assertTrue(profile.referral_code.startswith('SCB'))

    def test_invalid_referral_code_is_rejected(self):
        response = self.signup(referral_code='NOPE')
        self.assertContains(response, 'not valid')
        self.assertFalse(User.objects.filter(email='new@example.com').exists())

    def test_honeypot_blocks_bots(self):
        self.signup(website='http://spam.example')
        self.assertFalse(User.objects.filter(email='new@example.com').exists())


    def test_name_and_mobile_are_saved_and_number_can_log_in(self):
        self.signup(phone='+8801812-345678')
        user = User.objects.get(email='new@example.com')
        self.assertEqual((user.first_name, user.last_name), ('Nusrat', 'Jahan'))
        self.assertEqual(user.profile.phone, '01812345678')
        self.client.logout()
        response = self.client.post(reverse('account_login'), {'login': '01812345678', 'password': 'Str0ng-pass!'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_mobile_is_required_unique_and_bangladeshi(self):
        self.assertContains(self.signup(phone=''), 'This field is required')
        self.assertContains(self.signup(phone='12345'), 'Bangladeshi mobile number')
        self.signup()
        self.client.logout()
        response = self.signup(email='second@example.com')  # same number
        self.assertContains(response, 'already has an account')
        self.assertContains(response, 'Log in</a> instead')  # a real link, not escaped text
        self.assertNotContains(response, 'sent a code')
        self.assertFalse(User.objects.filter(email='second@example.com').exists())

    def test_accounts_without_a_number_can_still_log_in(self):
        User.objects.create_user('old', 'old@example.com', 'Str0ng-pass!')
        response = self.client.post(reverse('account_login'), {'login': 'old@example.com', 'password': 'Str0ng-pass!'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('_auth_user_id', self.client.session)

    def test_honeypot_is_hidden_on_the_page(self):
        page = self.client.get(reverse('account_signup')).content.decode()
        self.assertNotIn('Leave this field empty', page.split('<footer')[0])
        self.assertIn('class="hp-wrap"', page)

class LoginLockoutTests(TestCase):
    def test_account_locked_after_repeated_failures(self):
        User.objects.create_user('u', 'u@example.com', 'Str0ng-pass!')
        for _ in range(settings.AXES_FAILURE_LIMIT):
            self.client.post(reverse('account_login'), {'login': 'u@example.com', 'password': 'wrong'})
        response = self.client.post(reverse('account_login'), {'login': 'u@example.com', 'password': 'Str0ng-pass!'})
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, 'Too many login attempts', status_code=429)


class NewsletterTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_subscribe_and_unsubscribe(self):
        data = self.client.post(reverse('newsletter_subscribe'), {'email': 'Fan@Example.com'}, **AJAX).json()
        self.assertTrue(data['ok'])
        subscriber = Subscriber.objects.get()
        self.assertEqual(subscriber.email, 'fan@example.com')
        self.client.post(reverse('newsletter_unsubscribe', args=[subscriber.token]))
        subscriber.refresh_from_db()
        self.assertFalse(subscriber.is_active)

    def test_honeypot_and_bad_email(self):
        bot = self.client.post(reverse('newsletter_subscribe'), {'email': 'a@b.com', 'website': 'x'}, **AJAX)
        self.assertEqual(bot.status_code, 400)
        bad = self.client.post(reverse('newsletter_subscribe'), {'email': 'nope'}, **AJAX)
        self.assertEqual(bad.status_code, 400)
        self.assertFalse(Subscriber.objects.exists())


class NotificationTests(TestCase):
    def test_bell_shows_unread_and_page_marks_read(self):
        user = User.objects.create_user('n', 'n@example.com', 'x')
        Notification.objects.create(user=user, message='Your order shipped', url='/orders/')
        self.client.force_login(user)
        self.assertContains(self.client.get('/'), 'Your order shipped')
        self.assertContains(self.client.get(reverse('notifications')), 'Your order shipped')
        self.assertFalse(Notification.objects.filter(is_read=False).exists())

    def test_open_ignores_offsite_urls(self):
        user = User.objects.create_user('n', 'n@example.com', 'x')
        note = Notification.objects.create(user=user, message='x', url='https://evil.example/')
        self.client.force_login(user)
        response = self.client.get(reverse('notification_open', args=[note.pk]))
        self.assertEqual(response.url, reverse('notifications'))


class ProfileTests(TestCase):
    def test_profile_shows_points_and_referral_link(self):
        user = User.objects.create_user('p', 'p@example.com', 'x')
        self.client.force_login(user)
        response = self.client.get(reverse('profile'))
        self.assertContains(response, user.profile.referral_code)
        self.assertContains(response, 'Reward points')
