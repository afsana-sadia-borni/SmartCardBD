from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.template.loader import render_to_string
from django.utils import timezone

from accounts.models import Subscriber
from core.tasks import send_email
from orders.models import Order
from products.models import Product

from .cart import CART_EMAIL_KEY, CART_REMINDED_KEY, CART_SESSION_ID, CART_UPDATED_KEY, parse_key


def _reminder_email(data):
    """Where to send a reminder for this session: the logged-in user's email, or the email a
    guest typed at checkout. Returns (email, user or None)."""
    user_id = data.get('_auth_user_id')
    if user_id:
        user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
        return (user.email, user) if user else ('', None)
    return data.get(CART_EMAIL_KEY, ''), None


def send_abandoned_cart_reminders(hours=24, dry_run=False):
    """Email customers (logged in, or guests who typed their email at checkout) whose cart has
    sat untouched for `hours`. One reminder per cart change. Returns how many were (or would be) sent."""
    cutoff = timezone.now() - timedelta(hours=hours)
    unsubscribed = set(Subscriber.objects.filter(is_active=False).values_list('email', flat=True))
    sent = 0
    for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        data = session.get_decoded()
        cart, updated = data.get(CART_SESSION_ID), data.get(CART_UPDATED_KEY)
        if not (cart and updated) or data.get(CART_REMINDED_KEY):
            continue
        updated = datetime.fromisoformat(updated)
        if updated > cutoff:
            continue
        email, user = _reminder_email(data)
        if not email or email.lower() in unsubscribed:
            continue
        # Skip if they have ordered since the cart last changed.
        orders = user.orders if user else Order.objects.filter(email__iexact=email)
        if orders.filter(created_at__gt=updated).exists():
            continue
        products = list(Product.objects.active().filter(id__in=[parse_key(k)[0] for k in cart]))
        if not products:
            continue
        if not dry_run:
            body = render_to_string('cart/emails/abandoned_cart.txt', {
                'user': user, 'products': products, 'site_name': settings.SITE_NAME, 'site_url': settings.SITE_URL,
            })
            send_email.delay(f'You left something in your cart - {settings.SITE_NAME}', body, [email])
            data[CART_REMINDED_KEY] = timezone.now().isoformat()
            session.session_data = Session.objects.encode(data)
            session.save(update_fields=['session_data'])
        sent += 1
    return sent
