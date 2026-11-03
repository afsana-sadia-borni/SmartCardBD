from celery import shared_task
from django.core.mail import EmailMessage
from django.db import transaction


# SMTP errors are OSErrors: retry a few times with backoff instead of losing the email.
@shared_task(autoretry_for=(OSError,), retry_backoff=True, max_retries=3)
def send_email(subject, body, to):
    EmailMessage(subject, body, None, to).send()


def queue_email(subject, body, to):
    """Send an email in the background once the current transaction commits."""
    to = [address for address in to if address]
    if to:
        transaction.on_commit(lambda: send_email.delay(subject, body, to))
