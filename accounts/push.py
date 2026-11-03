"""Web push: send a notification to every browser a customer turned notifications on in."""
import json

from django.conf import settings
from pywebpush import WebPushException, webpush

from .models import PushSubscription


def push_enabled():
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def send_push_to_user(user_id, title, body, url=''):
    """Returns how many browsers got it. Subscriptions the push service says are gone are deleted."""
    if not push_enabled():
        return 0
    payload = json.dumps({'title': title, 'body': body, 'url': url})
    sent = 0
    for sub in PushSubscription.objects.filter(user_id=user_id):
        try:
            webpush(
                subscription_info=sub.as_subscription_info(), data=payload, ttl=24 * 60 * 60,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={'sub': f'mailto:{settings.VAPID_ADMIN_EMAIL}'},
            )
            sent += 1
        except WebPushException as exc:
            # 404/410: the customer turned notifications off or the browser dropped the subscription.
            if exc.response is not None and exc.response.status_code in (404, 410):
                sub.delete()
    return sent
