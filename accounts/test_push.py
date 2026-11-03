from io import StringIO
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from pywebpush import WebPushException

from .models import PushSubscription
from .services import notify

AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
SUB = {'endpoint': 'https://push.example.com/abc', 'p256dh': 'key', 'auth': 'secret'}


@override_settings(VAPID_PUBLIC_KEY='public', VAPID_PRIVATE_KEY='private')
class PushTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('p', 'p@example.com', 'x')
        self.client.force_login(self.user)

    def test_subscribe_and_unsubscribe(self):
        self.assertContains(self.client.get(reverse('notifications')), 'js-push-box')
        self.assertTrue(self.client.post(reverse('push_subscribe'), SUB, **AJAX).json()['ok'])
        self.assertEqual(PushSubscription.objects.get().user, self.user)
        self.client.post(reverse('push_unsubscribe'), {'endpoint': SUB['endpoint']}, **AJAX)
        self.assertFalse(PushSubscription.objects.exists())

    def test_rejects_non_https_endpoint(self):
        response = self.client.post(reverse('push_subscribe'), {**SUB, 'endpoint': 'http://evil/'}, **AJAX)
        self.assertEqual(response.status_code, 400)

    def test_notify_sends_push_and_drops_expired_subscriptions(self):
        self.client.post(reverse('push_subscribe'), SUB, **AJAX)
        with mock.patch('accounts.push.webpush') as webpush, self.captureOnCommitCallbacks(execute=True):
            notify(self.user, 'Your order shipped', url='/orders/')
        self.assertIn('Your order shipped', webpush.call_args.kwargs['data'])

        gone = WebPushException('gone', response=mock.Mock(status_code=410))
        with mock.patch('accounts.push.webpush', side_effect=gone), self.captureOnCommitCallbacks(execute=True):
            notify(self.user, 'Again')
        self.assertFalse(PushSubscription.objects.exists())


class PushOffTests(TestCase):
    def test_hidden_without_keys(self):
        user = User.objects.create_user('p', 'p@example.com', 'x')
        self.client.force_login(user)
        self.assertNotContains(self.client.get(reverse('notifications')), 'js-push-box')

    def test_generate_vapid_keys(self):
        out = StringIO()
        call_command('generate_vapid_keys', stdout=out)
        self.assertIn('VAPID_PUBLIC_KEY=', out.getvalue())
        self.assertIn('VAPID_PRIVATE_KEY=', out.getvalue())
