"""Steadfast courier: book a parcel for an order and follow its delivery status.

API: https://portal.packzy.com/api/v1 with the Api-Key and Secret-Key headers from the Steadfast portal.
"""
import logging

import requests
from django.conf import settings
from django.db import transaction

from .models import Order

logger = logging.getLogger(__name__)
TIMEOUT = 20
COURIER = 'Steadfast'
# Steadfast delivery_status -> what it means for our order.
DELIVERED = {'delivered', 'partial_delivered'}
CANCELLED = {'cancelled'}


class CourierError(Exception):
    pass


def steadfast_enabled():
    return bool(settings.STEADFAST_API_KEY and settings.STEADFAST_SECRET_KEY)


def _request(method, path, payload=None):
    try:
        response = requests.request(method, settings.STEADFAST_BASE_URL + path, json=payload, timeout=TIMEOUT, headers={
            'Api-Key': settings.STEADFAST_API_KEY, 'Secret-Key': settings.STEADFAST_SECRET_KEY,
            'Content-Type': 'application/json',
        })
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise CourierError('Could not reach Steadfast. Please try again.') from exc
    if response.status_code >= 400 or str(data.get('status')) not in ('200', 'None'):
        message = data.get('message') or data.get('errors') or f'HTTP {response.status_code}'
        raise CourierError(f'Steadfast refused it: {message}')
    return data


def cod_amount(order):
    """What the courier collects: the order total for unpaid Cash on Delivery, otherwise nothing."""
    if order.payment_method == Order.PaymentMethod.COD and order.payment_status != Order.PaymentStatus.PAID:
        return order.total
    return 0


def book_steadfast(order):
    """Create the parcel at Steadfast and mark the order shipped. Returns the order."""
    if not steadfast_enabled():
        raise CourierError('Steadfast is not set up (STEADFAST_API_KEY / STEADFAST_SECRET_KEY).')
    if order.courier_consignment_id:
        raise CourierError(f'Already booked with {order.courier_name} ({order.courier_tracking_code}).')
    if order.status not in (Order.Status.PENDING, Order.Status.CONFIRMED):
        raise CourierError(f'A {order.get_status_display().lower()} order can\'t be booked.')
    address = ', '.join(part for part in (order.address_line, order.area, order.upazila, order.district) if part)
    data = _request('POST', '/create_order', {
        'invoice': order.order_number,
        'recipient_name': order.full_name[:100],
        'recipient_phone': order.phone,
        'recipient_address': address[:250],
        'cod_amount': float(cod_amount(order)),
        'note': (order.note or '')[:200],
    })
    consignment = data.get('consignment') or {}
    if not consignment.get('consignment_id'):
        raise CourierError('Steadfast did not return a consignment id.')
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        order.courier_name = COURIER
        order.courier_consignment_id = str(consignment['consignment_id'])
        order.courier_tracking_code = consignment.get('tracking_code', '')
        order.courier_status = consignment.get('status', 'in_review')
        order.status = Order.Status.SHIPPED  # signals tell the customer, with the tracking link
        order.save()
    return order


def sync_steadfast_statuses():
    """Ask Steadfast about every shipped parcel; mark delivered orders delivered. Returns how many changed."""
    if not steadfast_enabled():
        return 0
    changed = 0
    shipped = Order.objects.filter(status=Order.Status.SHIPPED, courier_name=COURIER).exclude(courier_consignment_id='')
    for order in shipped:
        try:
            status = _request('GET', f'/status_by_cid/{order.courier_consignment_id}').get('delivery_status', '')
        except CourierError as exc:
            logger.warning('Steadfast status for %s failed: %s', order.order_number, exc)
            continue
        if not status or status == order.courier_status:
            continue
        order.courier_status = status
        fields = ['courier_status', 'updated_at']
        if status in DELIVERED:
            order.status = Order.Status.DELIVERED
            fields.append('status')
            changed += 1
        order.save(update_fields=fields)
    return changed
