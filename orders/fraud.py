"""Warning signs for Cash on Delivery orders that might be fake (refused at the door)."""
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from accounts.constants import normalize_bd_phone

from .models import BlockedPhone, Order


def is_blocked(phone):
    return BlockedPhone.objects.filter(phone=normalize_bd_phone(phone)).exists()


def cod_risk_flags(phone, amount):
    """Short, human-readable reasons to double-check a COD order. Empty list = looks fine."""
    phone = normalize_bd_phone(phone)
    flags = []
    history = Order.objects.filter(phone=phone).aggregate(
        total=Count('id'),
        delivered=Count('id', filter=Q(status=Order.Status.DELIVERED)),
        cancelled=Count('id', filter=Q(status=Order.Status.CANCELLED)),
        recent=Count('id', filter=Q(created_at__gte=timezone.now() - timedelta(hours=24))),
    )
    if history['cancelled'] >= 2 and history['cancelled'] > history['delivered']:
        flags.append(f"Cancelled {history['cancelled']} of {history['total']} earlier orders")
    if history['recent'] >= 3:
        flags.append(f"{history['recent']} orders from this number in the last 24 hours")
    if not history['delivered'] and amount >= settings.COD_REVIEW_AMOUNT:
        flags.append(f'First Cash on Delivery order over ৳{settings.COD_REVIEW_AMOUNT:,}')
    return flags


def needs_cod_otp(flags):
    from core.sms import sms_enabled

    if not sms_enabled() or settings.COD_OTP == 'off':
        return False
    return settings.COD_OTP == 'always' or bool(flags)
