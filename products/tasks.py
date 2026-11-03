from celery import shared_task

from .images import make_webp_variants
from .services import send_due_price_alerts


@shared_task
def send_price_alerts():
    return send_due_price_alerts()


@shared_task
def make_webp_images(name):
    return make_webp_variants(name)
