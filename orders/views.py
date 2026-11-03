import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.models import Address
from accounts.services import redeemable
from cart.cart import Cart
from core.ratelimit import hit_limit

from . import payments
from .forms import CheckoutForm, ReturnRequestForm, TrackOrderForm
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
        messages.error(request, f'{exc} You can retry payment from the order page.')
        return redirect(order)


def checkout(request):
    cart = Cart(request)
    if cart.is_empty():
        messages.info(request, 'Your cart is empty.')
        return redirect('cart_summary')

    user = request.user
    if request.method == 'POST':
        # Free up stock held by abandoned online payments before checking availability.
        # (Also available as a cron job: `python manage.py release_unpaid_orders`.)
        release_unpaid_orders()
        form = CheckoutForm(request.POST, user=user)
        if form.is_valid():
            payment_method, payment_channel = form.payment()
            try:
                order = create_order(
                    cart, form.shipping_data(), user=user,
                    payment_method=payment_method, payment_channel=payment_channel,
                    gift_wrap=form.cleaned_data.get('gift_wrap', False),
                    use_points=form.cleaned_data.get('use_points', False),
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

            if order.payment_method == Order.PaymentMethod.SSLCOMMERZ:
                return _start_online_payment(request, order)
            return redirect('order_success', order_number=order.order_number)
    else:
        initial = {}
        if user.is_authenticated:
            initial['email'] = user.email
            address = user.addresses.first()
            if address:
                initial.update(full_name=address.full_name, phone=address.phone, district=address.district,
                               upazila=address.upazila, area=address.area, address_line=address.address_line)
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
        messages.success(request, f'Order {order.order_number} has been cancelled.')
    except CheckoutError as exc:
        messages.error(request, str(exc))
    return redirect(order)


def track_order(request):
    """Order status for guests: order number + the phone number used at checkout."""
    order = None
    form = TrackOrderForm(request.POST or None)
    if request.method == 'POST':
        if hit_limit(request, 'track', limit=10, window_seconds=600):
            messages.error(request, 'Too many attempts. Please wait a few minutes and try again.')
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
        messages.error(request, 'A return can be requested within '
                                f'{settings.RETURN_WINDOW_DAYS} days of delivery, once per order.')
        return redirect(order)
    form = ReturnRequestForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        ReturnRequest.objects.create(order=order, **form.cleaned_data)
        messages.success(request, 'Return request sent. We will get back to you within 2 working days.')
        return redirect(order)
    return render(request, 'orders/return_request.html', {'order': order, 'form': form})


@require_POST
def order_pay(request, order_number):
    order = _get_viewable_order(request, order_number)
    if not order.can_pay_online:
        messages.error(request, 'This order cannot be paid online.')
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
        messages.error(request, 'Payment failed. Your order is saved. You can try paying again.')
    else:
        messages.warning(request, 'Payment was cancelled. Your order is saved. You can pay later or cancel it.')
    return redirect('order_detail', order_number=order_number)
