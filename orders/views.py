import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.translation import gettext as _

from accounts.constants import normalize_bd_phone
from accounts.models import Address
from accounts.services import redeemable
from cart.cart import Cart
from core.ratelimit import hit_limit
from core.sms import SMSError, send_sms

from . import payments
from .forms import CheckoutForm, ReturnRequestForm, TrackOrderForm
from .fraud import cod_risk_flags, is_blocked, needs_cod_otp
from .invoice import render_invoice
from .models import Order, ReturnRequest
from .services import (CheckoutError, cancel_order, create_order, delivery_zone_table, mark_order_paid,
                       release_unpaid_orders)

GUEST_ORDERS_SESSION_KEY = 'guest_orders'


def _remember_guest_order(request, order):
    orders = request.session.get(GUEST_ORDERS_SESSION_KEY, [])
    if order.order_number not in orders:
        request.session[GUEST_ORDERS_SESSION_KEY] = (orders + [order.order_number])[-20:]


def _get_viewable_order(request, order_number):
    """Owners can view their orders; guests can view orders placed in this browser session."""
    order = get_object_or_404(Order.objects.prefetch_related('items__product'), order_number=order_number)
    user = request.user
    if user.is_staff or (order.user_id and order.user_id == user.id):
        return order
    if not order.user_id and order_number in request.session.get(GUEST_ORDERS_SESSION_KEY, []):
        return order
    raise Http404


def _start_online_payment(request, order):
    try:
        return redirect(payments.init_payment(order, request))
    except payments.PaymentError as exc:
        messages.error(request, _('{error} You can retry payment from the order page.').format(error=exc))
        return redirect(order)


COD_OTP_SESSION_KEY = 'cod_otp'
COD_VERIFIED_SESSION_KEY = 'cod_verified_phone'
COD_OTP_MINUTES = 10
COD_OTP_MAX_ATTEMPTS = 5


def _otp_hash(code):
    return hmac.new(settings.SECRET_KEY.encode(), code.encode(), hashlib.sha256).hexdigest()


def _send_cod_otp(request, phone, post_data):
    """Text a 6-digit code and keep the checkout form until it is confirmed. False if the SMS failed."""
    code = f'{secrets.randbelow(10 ** 6):06d}'
    try:
        send_sms(phone, f'{code} is your {settings.SITE_NAME} order code. It expires in {COD_OTP_MINUTES} minutes.')
    except SMSError:
        return False
    request.session[COD_OTP_SESSION_KEY] = {
        'phone': phone, 'hash': _otp_hash(code), 'attempts': 0, 'post': post_data,
        'expires': (timezone.now() + timedelta(minutes=COD_OTP_MINUTES)).isoformat(),
    }
    return True


def _place_order(request, cart, form):
    """Create the order from a valid checkout form. Returns a response, or None to show the form again."""
    user = request.user
    payment_method, payment_channel = form.payment()
    risk_flags = []
    if payment_method == Order.PaymentMethod.COD:
        phone = normalize_bd_phone(form.cleaned_data['phone'])
        if is_blocked(phone):
            form.add_error('payment_method', _("Cash on Delivery isn't available for this number. "
                                               'Please pay online, or contact us.'))
            return None
        risk_flags = cod_risk_flags(phone, cart.get_total())
        verified = request.session.get(COD_VERIFIED_SESSION_KEY) == phone
        if needs_cod_otp(risk_flags) and not verified:
            if _send_cod_otp(request, phone, request.POST.dict()):
                return redirect('checkout_verify')
            # The SMS couldn't be sent: take the order, but staff see the warnings before confirming.
        if verified:
            risk_flags = [*risk_flags, 'Phone confirmed with an SMS code']
    try:
        order = create_order(
            cart, form.shipping_data(), user=user,
            payment_method=payment_method, payment_channel=payment_channel,
            gift_wrap=form.cleaned_data.get('gift_wrap', False),
            use_points=form.cleaned_data.get('use_points', False),
            risk_flags=risk_flags,
        )
    except CheckoutError as exc:
        messages.error(request, str(exc))
        return redirect('cart_summary')

    if user.is_authenticated and form.cleaned_data.get('save_address'):
        data = form.shipping_data()
        Address.objects.get_or_create(
            user=user, phone=data['phone'], district=data['district'], upazila=data['upazila'],
            area=data['area'], address_line=data['address_line'],
            defaults={'full_name': data['full_name']},
        )
    if not user.is_authenticated:
        _remember_guest_order(request, order)
    cart.clear()
    request.session.pop(COD_VERIFIED_SESSION_KEY, None)

    if order.payment_method == Order.PaymentMethod.SSLCOMMERZ:
        return _start_online_payment(request, order)
    return redirect('order_success', order_number=order.order_number)


def checkout(request):
    cart = Cart(request)
    if cart.is_empty():
        messages.info(request, _('Your cart is empty.'))
        return redirect('cart_summary')

    user = request.user
    if request.method == 'POST':
        # Free up stock held by abandoned online payments before checking availability.
        # (Also available as a cron job: `python manage.py release_unpaid_orders`.)
        release_unpaid_orders()
        form = CheckoutForm(request.POST, user=user)
        if form.is_valid():
            response = _place_order(request, cart, form)
            if response is not None:
                return response
    else:
        initial = {}
        if user.is_authenticated:
            initial['email'] = user.email
            address = user.addresses.first()
            if address:
                initial.update(full_name=address.full_name, phone=address.phone, district=address.district,
                               upazila=address.upazila, area=address.area, address_line=address.address_line)
            elif getattr(user, 'profile', None) and user.profile.phone:
                initial.update(full_name=user.get_full_name(), phone=user.profile.phone)
        form = CheckoutForm(initial=initial, user=user)

    points_used, points_discount = redeemable(form.points, cart.get_total())
    return render(request, 'orders/checkout.html', {
        'form': form,
        'zones': delivery_zone_table(),
        'free_shipping_min': settings.FREE_SHIPPING_MIN,
        'gift_wrap_price': settings.GIFT_WRAP_PRICE,
        'points_available': form.points,
        'points_usable': points_used,
        'points_discount': points_discount,
    })


def checkout_verify(request):
    """Confirm the phone of a Cash on Delivery order with the SMS code, then place the order."""
    pending = request.session.get(COD_OTP_SESSION_KEY)
    cart = Cart(request)
    if not pending or cart.is_empty():
        return redirect('checkout')
    error = ''
    if request.method == 'POST' and request.POST.get('resend'):
        if hit_limit(request, 'cod-otp-resend', limit=3, window_seconds=900):
            error = _('Too many codes sent. Please wait a few minutes.')
        elif _send_cod_otp(request, pending['phone'], pending['post']):
            messages.info(request, _('A new code is on its way.'))
            return redirect('checkout_verify')
        else:
            error = _('We could not send a code right now. Please try again.')
    elif request.method == 'POST':
        expired = timezone.now() > datetime.fromisoformat(pending['expires'])
        pending['attempts'] += 1
        request.session[COD_OTP_SESSION_KEY] = pending
        if expired or pending['attempts'] > COD_OTP_MAX_ATTEMPTS:
            error = _('This code has expired. Send a new one.')
        elif hmac.compare_digest(_otp_hash(request.POST.get('code', '').strip()), pending['hash']):
            request.session.pop(COD_OTP_SESSION_KEY)
            request.session[COD_VERIFIED_SESSION_KEY] = pending['phone']
            form = CheckoutForm(pending['post'], user=request.user)
            if form.is_valid():
                response = _place_order(request, cart, form)
                if response is not None:
                    return response
            messages.error(request, _('Please check your details and place the order again.'))
            return redirect('checkout')
        else:
            error = _('That code is not right. Please check the SMS and try again.')
    return render(request, 'orders/checkout_verify.html', {'phone': pending['phone'], 'error': error})


def order_success(request, order_number):
    order = _get_viewable_order(request, order_number)
    return render(request, 'orders/order_success.html', {'order': order})


@login_required
def order_list(request):
    orders = request.user.orders.prefetch_related('items')
    return render(request, 'orders/order_list.html', {'orders': orders})


def order_detail(request, order_number):
    order = _get_viewable_order(request, order_number)
    return render(request, 'orders/order_detail.html', {'order': order})


def order_invoice(request, order_number):
    order = _get_viewable_order(request, order_number)
    response = HttpResponse(render_invoice(order), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="invoice-{order.order_number}.pdf"'
    return response


@require_POST
def order_cancel(request, order_number):
    order = _get_viewable_order(request, order_number)
    try:
        cancel_order(order)
        messages.success(request, _('Order {number} has been cancelled.').format(number=order.order_number))
    except CheckoutError as exc:
        messages.error(request, str(exc))
    return redirect(order)


def track_order(request):
    """Order status for guests: order number + the phone number used at checkout."""
    order = None
    form = TrackOrderForm(request.POST or None)
    if request.method == 'POST':
        if hit_limit(request, 'track', limit=10, window_seconds=600):
            messages.error(request, _('Too many attempts. Please wait a few minutes and try again.'))
        elif form.is_valid():
            phone = re.sub(r'^(\+?88)', '', form.cleaned_data['phone'])
            order = (
                Order.objects.prefetch_related('items')
                .filter(order_number__iexact=form.cleaned_data['order_number'].strip(), phone__endswith=phone)
                .first()
            )
            if order is None:
                form.add_error(None, 'No order matches that order number and phone number.')
    return render(request, 'orders/track.html', {'form': form, 'order': order})


@login_required
def return_request(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    if not order.can_request_return:
        messages.error(request, _('A return can be requested within {days} days of delivery, once per order.').format(
            days=settings.RETURN_WINDOW_DAYS))
        return redirect(order)
    form = ReturnRequestForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        ReturnRequest.objects.create(order=order, **form.cleaned_data)
        messages.success(request, _('Return request sent. We will get back to you within 2 working days.'))
        return redirect(order)
    return render(request, 'orders/return_request.html', {'order': order, 'form': form})


@require_POST
def order_pay(request, order_number):
    order = _get_viewable_order(request, order_number)
    if not order.can_pay_online:
        messages.error(request, _('This order cannot be paid online.'))
        return redirect(order)
    return _start_online_payment(request, order)


# SSLCommerz callbacks. The gateway POSTs here from its own domain, so there is
# no CSRF token and (with SameSite cookies) usually no session either.

def _order_from_gateway(request):
    return Order.objects.filter(order_number=request.POST.get('tran_id', '')).first()


@csrf_exempt
@require_POST
def payment_success(request):
    order = _order_from_gateway(request)
    if order is None:
        raise Http404
    val_id = request.POST.get('val_id')
    if payments.validate_payment(val_id, order):
        mark_order_paid(order, val_id)
        return redirect('order_success', order_number=order.order_number)
    Order.objects.filter(pk=order.pk).exclude(payment_status=Order.PaymentStatus.PAID).update(
        payment_status=Order.PaymentStatus.FAILED,
    )
    return redirect('payment_result', order_number=order.order_number, result='failed')


@csrf_exempt
@require_POST
def payment_fail(request):
    order = _order_from_gateway(request)
    if order is None:
        raise Http404
    Order.objects.filter(pk=order.pk).exclude(payment_status=Order.PaymentStatus.PAID).update(
        payment_status=Order.PaymentStatus.FAILED,
    )
    return redirect('payment_result', order_number=order.order_number, result='failed')


@csrf_exempt
@require_POST
def payment_cancel(request):
    order = _order_from_gateway(request)
    if order is None:
        raise Http404
    return redirect('payment_result', order_number=order.order_number, result='cancelled')


@csrf_exempt
@require_POST
def payment_ipn(request):
    order = _order_from_gateway(request)
    if order and payments.validate_payment(request.POST.get('val_id'), order):
        mark_order_paid(order, request.POST['val_id'])
        return HttpResponse('OK')
    return HttpResponse('INVALID', status=400)


def payment_result(request, order_number, result):
    if result not in ('failed', 'cancelled'):
        raise Http404
    if result == 'failed':
        messages.error(request, _('Payment failed. Your order is saved. You can try paying again.'))
    else:
        messages.warning(request, _('Payment was cancelled. Your order is saved. You can pay later or cancel it.'))
    return redirect('order_detail', order_number=order_number)
