from celery import shared_task

from .services import send_abandoned_cart_reminders


@shared_task
def send_abandoned_cart_emails(hours=24):
    return send_abandoned_cart_reminders(hours)
