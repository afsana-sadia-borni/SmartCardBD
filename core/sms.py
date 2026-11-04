"""Text messages (SMS). Without an SMS provider the message is logged, like the console email backend.

Provider: BulkSMSBD (https://bulksmsbd.net). Set SMS_API_KEY and SMS_SENDER_ID in .env.
"""
import logging

import requests
from django.conf import settings

from accounts.constants import normalize_bd_phone

logger = logging.getLogger(__name__)
BULKSMSBD_URL = 'https://bulksmsbd.net/api/smsapi'
TIMEOUT = 15


class SMSError(Exception):
    pass


def sms_enabled():
    return bool(settings.SMS_API_KEY and settings.SMS_SENDER_ID)


def send_sms(phone, message):
    """Send one SMS to a Bangladeshi mobile number. Raises SMSError if the provider refuses it."""
    phone = normalize_bd_phone(phone)
    if not phone:
        raise SMSError('Not a Bangladeshi mobile number.')
    if not sms_enabled():
        logger.info('SMS to %s (no SMS provider set, not sent): %s', phone, message)
        return 'console'
    try:
        response = requests.post(BULKSMSBD_URL, timeout=TIMEOUT, data={
            'api_key': settings.SMS_API_KEY, 'senderid': settings.SMS_SENDER_ID,
            'number': '88' + phone, 'message': message,
        })
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise SMSError('Could not reach the SMS provider.') from exc
    if str(data.get('response_code')) != '202':
        raise SMSError(f"SMS provider error {data.get('response_code')}: {data.get('error_message', '')}".strip())
    return 'sent'
