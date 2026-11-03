from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import CustomerProfile, Notification, PointTransaction, get_profile


def notify(user, message, url='', icon='bell', email_subject=None):
    """In-app notification (the bell), optionally also emailed."""
    if user is None:
        return None
    note = Notification.objects.create(user=user, message=message[:255], url=url, icon=icon)
    if email_subject and user.email:
        body = message + (f'\n\n{url}' if url else '') + f'\n\n- {settings.SITE_NAME}'
        transaction.on_commit(lambda: send_mail(email_subject, body, None, [user.email], fail_silently=True))
    return note


def points_for_amount(amount):
    return int(Decimal(amount) // settings.POINTS_PER_TAKA)


def redeemable(points, amount):
    """How many points can be spent on an order of `amount`, and the taka discount: (points, discount)."""
    blocks = min(points // settings.POINTS_REDEEM_BLOCK, int(Decimal(amount) // settings.POINTS_REDEEM_VALUE))
    blocks = max(blocks, 0)
    return blocks * settings.POINTS_REDEEM_BLOCK, Decimal(blocks * settings.POINTS_REDEEM_VALUE)


def change_points(user, points, reason, order=None):
    get_profile(user)
    CustomerProfile.objects.filter(user=user).update(points=F('points') + points)
    PointTransaction.objects.create(user=user, points=points, reason=reason, order=order)


@transaction.atomic
def award_order_points(order):
    """Credit reward points once an order is delivered (1 point per ৳100 paid)."""
    from orders.models import Order

    order = Order.objects.select_for_update().get(pk=order.pk)
    if not order.user_id or order.points_earned:
        return 0
    points = points_for_amount(order.total - order.shipping_cost)
    if points <= 0:
        return 0
    change_points(order.user, points, f'Order {order.order_number} delivered', order)
    Order.objects.filter(pk=order.pk).update(points_earned=points)
    notify(order.user, f'You earned {points} reward points for order {order.order_number}.',
           url='/profile/', icon='star')
    return points


def refund_order_points(order):
    """Give back points spent on an order that was cancelled."""
    if order.user_id and order.points_used:
        change_points(order.user, order.points_used, f'Order {order.order_number} cancelled', order)


@transaction.atomic
def reward_referral(order):
    """When a referred customer's first order is delivered, both people get a coupon."""
    from orders.models import Coupon, Order

    if not order.user_id:
        return False
    profile = CustomerProfile.objects.select_for_update().filter(user_id=order.user_id).first()
    if not profile or not profile.referred_by_id or profile.referral_rewarded:
        return False
    delivered = Order.objects.filter(user_id=order.user_id, status=Order.Status.DELIVERED).count()
    if delivered != 1:
        return False
    amount = Decimal(settings.REFERRAL_REWARD)
    for user, text in [(profile.user, 'Thanks for joining with a referral!'),
                       (profile.referred_by, f'Your friend {profile.user.email} placed their first order!')]:
        coupon = Coupon.objects.create(
            code=f'REF{profile.referral_code[-4:]}{user.id}{timezone.now():%H%M%S}'[:30],
            discount_type=Coupon.FLAT, value=amount, user=user, usage_limit=1,
            valid_to=timezone.now() + timedelta(days=90),
        )
        notify(user, f'{text} Here is a ৳{amount:,.0f} coupon: {coupon.code}', url='/cart/', icon='gift',
               email_subject=f'Your ৳{amount:,.0f} {settings.SITE_NAME} coupon')
    profile.referral_rewarded = True
    profile.save(update_fields=['referral_rewarded'])
    return True
