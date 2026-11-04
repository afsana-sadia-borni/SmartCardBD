import logging

from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.db import transaction

logger = logging.getLogger(__name__)


# SMTP errors are OSErrors: retry a few times with backoff instead of losing the email.
@shared_task(autoretry_for=(OSError,), retry_backoff=True, max_retries=3)
def send_email(subject, body, to, html=None):
    message = EmailMultiAlternatives(subject, body, None, to)
    if html:
        message.attach_alternative(html, 'text/html')
    message.send()


def queue_email(subject, body, to, html=None):
    """Send an email in the background once the current transaction commits."""
    to = [address for address in to if address]
    if to:
        transaction.on_commit(lambda: send_email.delay(subject, body, to, html))


@shared_task(autoretry_for=(OSError,), retry_backoff=True, max_retries=3)
def send_sms_task(phone, message):
    from .sms import SMSError, send_sms

    try:
        return send_sms(phone, message)
    except SMSError as exc:
        # A wrong number or an empty balance won't fix itself, so log it instead of retrying.
        logger.warning('SMS to %s failed: %s', phone, exc)
        return 'failed'


def queue_sms(phone, message):
    """Send an SMS in the background once the current transaction commits."""
    if phone:
        transaction.on_commit(lambda: send_sms_task.delay(phone, message))
