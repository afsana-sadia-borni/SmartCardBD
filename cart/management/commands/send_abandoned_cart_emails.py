from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone

from cart.cart import CART_REMINDED_KEY, CART_SESSION_ID, CART_UPDATED_KEY, parse_key
from products.models import Product


class Command(BaseCommand):
    help = "Email logged-in customers who left items in their cart (run it from cron, e.g. hourly)."

    def add_arguments(self, parser):
        parser.add_argument('--hours', type=int, default=24, help='How long a cart must sit untouched.')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, hours, dry_run, **options):
        cutoff = timezone.now() - timedelta(hours=hours)
        User = get_user_model()
        sent = 0
        for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
            data = session.get_decoded()
            user_id = data.get('_auth_user_id')
            cart = data.get(CART_SESSION_ID)
            updated = data.get(CART_UPDATED_KEY)
            if not (user_id and cart and updated) or data.get(CART_REMINDED_KEY):
                continue
            if datetime.fromisoformat(updated) > cutoff:
                continue
            user = User.objects.filter(pk=user_id, is_active=True).first()
            if user is None or not user.email:
                continue
            # Skip if they have ordered since the cart last changed.
            if user.orders.filter(created_at__gt=datetime.fromisoformat(updated)).exists():
                continue
            product_ids = [parse_key(k)[0] for k in cart]
            products = list(Product.objects.active().filter(id__in=product_ids))
            if not products:
                continue
            if not dry_run:
                body = render_to_string('cart/emails/abandoned_cart.txt', {
                    'user': user, 'products': products, 'site_name': settings.SITE_NAME,
                })
                send_mail(f'You left something in your cart - {settings.SITE_NAME}', body, None, [user.email],
                          fail_silently=True)
                data[CART_REMINDED_KEY] = timezone.now().isoformat()
                session.session_data = Session.objects.encode(data)
                session.save(update_fields=['session_data'])
            sent += 1
        self.stdout.write(self.style.SUCCESS(f'{"Would send" if dry_run else "Sent"} {sent} reminder(s).'))
