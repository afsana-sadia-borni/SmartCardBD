"""SSLCommerz payment gateway (v4 API).

Docs: https://developer.sslcommerz.com/doc/v4/
Flow: init_payment() -> customer pays on the gateway -> gateway POSTs back to
our success/fail/cancel URLs and (server-to-server) to the IPN URL. We never
trust that POST on its own: every success is re-checked with validate_payment().
"""
from decimal import Decimal

import requests
from django.conf import settings
from django.urls import reverse

TIMEOUT = 15


class PaymentError(Exception):
    pass


def is_configured():
    return bool(settings.SSLCOMMERZ_STORE_ID and settings.SSLCOMMERZ_STORE_PASSWORD)


def _base_url():
    return 'https://sandbox.sslcommerz.com' if settings.SSLCOMMERZ_SANDBOX else 'https://securepay.sslcommerz.com'


def init_payment(order, request):
    """Create a gateway session and return the URL to redirect the customer to."""
    if not is_configured():
        raise PaymentError('Online payment is not configured.')

    def absolute(name):
        return request.build_absolute_uri(reverse(name))

    payload = {
        'store_id': settings.SSLCOMMERZ_STORE_ID,
        'store_passwd': settings.SSLCOMMERZ_STORE_PASSWORD,
        'total_amount': str(order.total),
        'currency': 'BDT',
        'tran_id': order.order_number,
        'success_url': absolute('payment_success'),
        'fail_url': absolute('payment_fail'),
        'cancel_url': absolute('payment_cancel'),
        'ipn_url': absolute('payment_ipn'),
        'cus_name': order.full_name,
        'cus_email': order.email,
        'cus_phone': order.phone,
        'cus_add1': order.address_line,
        'cus_city': order.district,
        'cus_country': 'Bangladesh',
        'shipping_method': 'Courier',
        'ship_name': order.full_name,
        'ship_add1': f'{order.address_line}, {order.area}',
        'ship_city': order.district,
        'ship_postcode': '0000',
        'ship_country': 'Bangladesh',
        'num_of_item': order.item_count,
        'product_name': ', '.join(i.product_title for i in order.items.all())[:255],
        'product_category': 'General',
        'product_profile': 'general',
    }
    try:
        response = requests.post(f'{_base_url()}/gwprocess/v4/api.php', data=payload, timeout=TIMEOUT)
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise PaymentError('Could not reach the payment gateway. Please try again.') from exc

    if data.get('status') != 'SUCCESS' or not data.get('GatewayPageURL'):
        raise PaymentError(data.get('failedreason') or 'Payment gateway rejected the request.')
    return data['GatewayPageURL']


def validate_payment(val_id, order):
    """Ask SSLCommerz whether val_id is a genuine, completed payment for this order."""
    if not val_id:
        return False
    params = {
        'val_id': val_id,
        'store_id': settings.SSLCOMMERZ_STORE_ID,
        'store_passwd': settings.SSLCOMMERZ_STORE_PASSWORD,
        'format': 'json',
    }
    try:
        response = requests.get(
            f'{_base_url()}/validator/api/validationserverAPI.php', params=params, timeout=TIMEOUT,
        )
        data = response.json()
    except (requests.RequestException, ValueError):
        return False

    try:
        amount = Decimal(str(data.get('currency_amount') or data.get('amount') or '0'))
    except ArithmeticError:
        return False
    return (
        data.get('status') in ('VALID', 'VALIDATED')
        and data.get('tran_id') == order.order_number
        and data.get('currency_type', data.get('currency')) == 'BDT'
        and amount == order.total
    )
