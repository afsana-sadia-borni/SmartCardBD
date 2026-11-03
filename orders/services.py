from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F
from django.template.loader import render_to_string
from django.utils import timezone

from accounts.constants import INSIDE_DHAKA_DISTRICT
from accounts.models import CustomerProfile
from accounts.services import change_points, redeemable, refund_order_points
from products.bundles import bundle_discount
from products.models import Product, ProductVariant

from .models import Coupon, DeliveryZone, Order, OrderItem


class CheckoutError(Exception):
    """Raised when an order can't be placed (e.g. stock ran out). The message is user-facing."""


def delivery_info(district):
    """(charge, delivery time text) for a district, from the admin's delivery zones."""
    zone = DeliveryZone.for_district(district)
    if zone is not None:
        return zone.charge, zone.delivery_time
    if district == INSIDE_DHAKA_DISTRICT:
        return Decimal(settings.SHIPPING_INSIDE_DHAKA), '1-2 days'
    return Decimal(settings.SHIPPING_OUTSIDE_DHAKA), '3-5 days'


def calculate_shipping(amount, district):
    if amount <= 0:
        return Decimal('0.00')
    if amount >= settings.FREE_SHIPPING_MIN:
        return Decimal('0.00')
    return Decimal(delivery_info(district)[0])


def delivery_zone_table():
    """{district: {'charge': ..., 'time': ...}} for the checkout page's live estimate."""
    from accounts.constants import BD_DISTRICTS

    table = {}
    for district in BD_DISTRICTS:
        charge, time = delivery_info(district)
        table[district] = {'charge': float(charge), 'time': time}
    return table


@transaction.atomic
def create_order(cart, shipping, user=None, payment_method=Order.PaymentMethod.COD, gift_wrap=False,
                 use_points=False):
    """Turn the cart into an Order.

    Product and variant rows are locked with SELECT ... FOR UPDATE so two customers buying
    the last unit at the same moment can't both succeed. Prices are re-read from the locked
    rows, never trusted from the session.
    """
    from cart.cart import parse_key

    lines_in = [(parse_key(key), data['quantity']) for key, data in cart.cart.items()]
    if not lines_in:
        raise CheckoutError('Your cart is empty.')

    product_ids = sorted({pid for (pid, _), _ in lines_in})
    variant_ids = sorted({vid for (_, vid), _ in lines_in if vid})
    products = {
        p.id: p for p in Product.objects.select_for_update().filter(id__in=product_ids, is_active=True).order_by('id')
    }
    variants = {
        v.id: v for v in ProductVariant.objects.select_for_update().filter(id__in=variant_ids, is_active=True)
        .order_by('id')
    }

    subtotal = Decimal('0.00')
    lines = []
    for (pid, vid), qty in lines_in:
        product = products.get(pid)
        variant = variants.get(vid) if vid else None
        if product is None or (vid and (variant is None or variant.product_id != pid)):
            raise CheckoutError('A product in your cart is no longer available. Please review your cart.')
        if variant is None and product.variants.filter(is_active=True).exists():
            raise CheckoutError(f'Please choose an option for "{product.title}" in your cart.')
        if variant is not None:
            variant.product = product
        stock = variant.stock if variant else product.stock
        name = f'{product.title} ({variant.label})' if variant else product.title
        if stock < qty:
            raise CheckoutError(f'Only {stock} of "{name}" left in stock. Please update your cart.')
        price = variant.final_price if variant else product.final_price
        subtotal += price * qty
        lines.append((product, variant, qty, price))

    qty_by_product, price_by_product = {}, {}
    for product, _, qty, price in lines:
        qty_by_product[product.id] = qty_by_product.get(product.id, 0) + qty
        price_by_product[product.id] = min(price_by_product.get(product.id, price), price)
    bundle_saving, _ = bundle_discount(qty_by_product, price_by_product)

    coupon = None
    discount = Decimal('0.00')
    coupon_id = cart.session.get('coupon_id')
    if coupon_id:
        coupon = Coupon.objects.select_for_update().filter(id=coupon_id).first()
        if coupon is not None:
            ok, reason = coupon.is_valid_for(subtotal, user)
            if not ok:
                raise CheckoutError(f'Coupon "{coupon.code}" can no longer be used: {reason}')
            discount = coupon.calculate_discount(subtotal)

    goods_total = max(subtotal - discount - bundle_saving, Decimal('0.00'))

    points_used, points_discount = 0, Decimal('0.00')
    if use_points and user and user.is_authenticated:
        profile = CustomerProfile.objects.select_for_update().filter(user=user).first()
        if profile:
            points_used, points_discount = redeemable(profile.points, goods_total)
    goods_total -= points_discount

    shipping_cost = calculate_shipping(goods_total, shipping['district'])
    gift_wrap_cost = Decimal(settings.GIFT_WRAP_PRICE) if gift_wrap else Decimal('0.00')
    order = Order.objects.create(
        user=user if user and user.is_authenticated else None,
        coupon=coupon,
        subtotal=subtotal,
        discount=discount,
        bundle_discount=bundle_saving,
        points_used=points_used,
        points_discount=points_discount,
        gift_wrap=gift_wrap,
        gift_wrap_cost=gift_wrap_cost,
        shipping_cost=shipping_cost,
        delivery_estimate=delivery_info(shipping['district'])[1],
        total=goods_total + shipping_cost + gift_wrap_cost,
        payment_method=payment_method,
        **shipping,
    )
    OrderItem.objects.bulk_create([
        OrderItem(order=order, product=product, variant=variant, product_title=product.title,
                  variant_label=variant.label if variant else '', price=price, quantity=qty)
        for product, variant, qty, price in lines
    ])
    for product, variant, qty, _ in lines:
        # A product with variants keeps the total of its variants' stock.
        Product.objects.filter(pk=product.pk).update(stock=F('stock') - qty)
        if variant is not None:
            ProductVariant.objects.filter(pk=variant.pk).update(stock=F('stock') - qty)
    if coupon is not None:
        Coupon.objects.filter(pk=coupon.pk).update(used_count=F('used_count') + 1)
    if points_used:
        change_points(user, -points_used, f'Used on order {order.order_number}', order)

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
        if item.variant_id:
            ProductVariant.objects.filter(pk=item.variant_id).update(stock=F('stock') + item.quantity)
    if order.coupon_id:
        Coupon.objects.filter(pk=order.coupon_id, used_count__gt=0).update(used_count=F('used_count') - 1)
    refund_order_points(order)
    order.status = Order.Status.CANCELLED
    order.save(update_fields=['status', 'updated_at'])
    return order


def _reserve_stock_again(order):
    """Take stock for a cancelled order's items again. Returns False (and changes nothing) if any item ran out."""
    items = list(order.items.exclude(product__isnull=True))
    products = {
        p.id: p for p in Product.objects.select_for_update().filter(id__in=[i.product_id for i in items])
    }
    variants = {
        v.id: v for v in ProductVariant.objects.select_for_update().filter(
            id__in=[i.variant_id for i in items if i.variant_id])
    }
    if any(products[i.product_id].stock < i.quantity for i in items):
        return False
    if any(i.variant_id and (i.variant_id not in variants or variants[i.variant_id].stock < i.quantity)
           for i in items):
        return False
    if order.points_used:
        profile = CustomerProfile.objects.select_for_update().filter(user_id=order.user_id).first()
        if profile is None or profile.points < order.points_used:
            return False
        change_points(order.user, -order.points_used, f'Used on order {order.order_number}', order)
    for item in items:
        Product.objects.filter(pk=item.product_id).update(stock=F('stock') - item.quantity)
        if item.variant_id:
            ProductVariant.objects.filter(pk=item.variant_id).update(stock=F('stock') - item.quantity)
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
