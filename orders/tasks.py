from celery import shared_task

from .models import Order
from . import services


@shared_task(autoretry_for=(OSError,), retry_backoff=True, max_retries=3)
def send_order_email(order_id, kind):
    order = Order.objects.filter(pk=order_id).first()
    if order is not None:
        services.order_email(order, kind).send()


@shared_task
def release_unpaid_orders():
    return services.release_unpaid_orders()


@shared_task
def sync_courier_status():
    from .courier import sync_steadfast_statuses

    return sync_steadfast_statuses()
