from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F
from django.template.loader import render_to_string
from django.utils import timezone

from accounts.constants import INSIDE_DHAKA_DISTRICT
from products.models import Product

from .models import Coupon, Order, OrderItem


class CheckoutError(Exception):
    """Raised when an order can't be placed (e.g. stock ran out). The message is user-facing."""


def calculate_shipping(amount, district):
    if amount <= 0:
        return Decimal('0.00')
    if amount >= settings.FREE_SHIPPING_MIN:
        return Decimal('0.00')
    if district == INSIDE_DHAKA_DISTRICT:
        return Decimal(settings.SHIPPING_INSIDE_DHAKA)
    return Decimal(settings.SHIPPING_OUTSIDE_DHAKA)


@transaction.atomic
def create_order(cart, shipping, user=None, payment_method=Order.PaymentMethod.COD):
    """Turn the cart into an Order.

    Product rows are locked with SELECT ... FOR UPDATE so two customers buying
    the last unit at the same moment can't both succeed. Prices are re-read from
    the locked rows, never trusted from the session.
    """
    quantities = {int(pid): data['quantity'] for pid, data in cart.cart.items()}
    if not quantities:
        raise CheckoutError('Your cart is empty.')

    products = {
        p.id: p
        for p in Product.objects.select_for_update().filter(id__in=quantities, is_active=True).order_by('id')
    }

    subtotal = Decimal('0.00')
    lines = []
    for pid, qty in quantities.items():
        product = products.get(pid)
        if product is None:
            raise CheckoutError('A product in your cart is no longer available. Please review your cart.')
        if product.stock < qty:
            raise CheckoutError(
                f'Only {product.stock} of "{product.title}" left in stock. Please update your cart.'
            )
        price = product.final_price
        subtotal += price * qty
        lines.append((product, qty, price))

    coupon = None
    discount = Decimal('0.00')
    coupon_id = cart.session.get('coupon_id')
    if coupon_id:
        coupon = Coupon.objects.select_for_update().filter(id=coupon_id).first()
        if coupon is not None:
            ok, reason = coupon.is_valid_for(subtotal)
            if not ok:
                raise CheckoutError(f'Coupon "{coupon.code}" can no longer be used: {reason}')
            discount = coupon.calculate_discount(subtotal)

    shipping_cost = calculate_shipping(subtotal - discount, shipping['district'])

    order = Order.objects.create(
        user=user if user and user.is_authenticated else None,
        coupon=coupon,
        subtotal=subtotal,
        discount=discount,
        shipping_cost=shipping_cost,
        total=subtotal - discount + shipping_cost,
        payment_method=payment_method,
        **shipping,
    )
    OrderItem.objects.bulk_create([
        OrderItem(order=order, product=product, product_title=product.title, price=price, quantity=qty)
        for product, qty, price in lines
    ])
    for product, qty, _ in lines:
        Product.objects.filter(pk=product.pk).update(stock=F('stock') - qty)
    if coupon is not None:
        Coupon.objects.filter(pk=coupon.pk).update(used_count=F('used_count') + 1)

    transaction.on_commit(lambda: send_order_email(order, 'confirmation'))
    return order


@transaction.atomic
def cancel_order(order, by_staff=False):
    """Cancel an order and put its items back in stock.

    Customers can only cancel pending, unpaid orders; staff can cancel anything not yet delivered.
    """
    order = Order.objects.select_for_update().get(pk=order.pk)
    staff_allowed = order.status not in (Order.Status.DELIVERED, Order.Status.CANCELLED)
    if not (order.can_cancel or (by_staff and staff_allowed)):
        raise CheckoutError('This order can no longer be cancelled.')
    for item in order.items.all():
        if item.product_id:
            Product.objects.filter(pk=item.product_id).update(stock=F('stock') + item.quantity)
    if order.coupon_id:
        Coupon.objects.filter(pk=order.coupon_id, used_count__gt=0).update(used_count=F('used_count') - 1)
    order.status = Order.Status.CANCELLED
    order.save(update_fields=['status', 'updated_at'])
    return order


def _reserve_stock_again(order):
    """Take stock for a cancelled order's items again. Returns False (and changes nothing) if any item ran out."""
    items = list(order.items.exclude(product__isnull=True))
    products = {
        p.id: p for p in Product.objects.select_for_update().filter(id__in=[i.product_id for i in items])
    }
    if any(products[i.product_id].stock < i.quantity for i in items):
        return False
    for item in items:
        Product.objects.filter(pk=item.product_id).update(stock=F('stock') - item.quantity)
    if order.coupon_id:
        Coupon.objects.filter(pk=order.coupon_id).update(used_count=F('used_count') + 1)
    return True


@transaction.atomic
def mark_order_paid(order, transaction_id):
    """Idempotently mark an order as paid (called from the payment success page and IPN).

    If the order was auto-cancelled while the customer was still paying, it is revived when
    the stock is still available; otherwise it stays cancelled and paid, which staff refund.
    """
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.payment_status == Order.PaymentStatus.PAID:
        return order
    order.payment_status = Order.PaymentStatus.PAID
    order.transaction_id = transaction_id
    if order.status == Order.Status.PENDING:
        order.status = Order.Status.CONFIRMED
    elif order.status == Order.Status.CANCELLED and _reserve_stock_again(order):
        order.status = Order.Status.CONFIRMED
    order.save(update_fields=['payment_status', 'transaction_id', 'status', 'updated_at'])
    return order


def release_unpaid_orders(older_than=None):
    """Cancel online-payment orders left unpaid for too long, so their stock goes back on sale.

    Returns the number of orders cancelled.
    """
    older_than = older_than or timedelta(minutes=settings.UNPAID_ORDER_TIMEOUT_MINUTES)
    stale = Order.objects.filter(
        payment_method=Order.PaymentMethod.SSLCOMMERZ,
        status=Order.Status.PENDING,
        created_at__lt=timezone.now() - older_than,
    ).exclude(payment_status=Order.PaymentStatus.PAID)

    released = 0
    for order in stale:
        try:
            cancel_order(order)
            released += 1
        except CheckoutError:
            pass  # paid or changed in the meantime
    return released


EMAIL_SUBJECTS = {
    'confirmation': 'Order {number} received - SmartCart BD',
    'status': 'Order {number} is now {status} - SmartCart BD',
}


def send_order_email(order, kind):
    subject = EMAIL_SUBJECTS[kind].format(number=order.order_number, status=order.get_status_display())
    body = render_to_string(f'orders/emails/order_{kind}.txt', {'order': order, 'site_name': settings.SITE_NAME})
    send_mail(subject, body, None, [order.email], fail_silently=True)
