from django.core.management.base import BaseCommand, CommandError

from core.sms import SMSError, send_sms, sms_enabled


class Command(BaseCommand):
    help = 'Send a test SMS, to check SMS_API_KEY and SMS_SENDER_ID in .env.'

    def add_arguments(self, parser):
        parser.add_argument('phone', help='Mobile number, e.g. 01712345678.')

    def handle(self, *args, phone, **options):
        try:
            send_sms(phone, 'Test SMS from your shop. SMS sending works.')
        except SMSError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS('Sent.' if sms_enabled() else 'Logged only: no SMS provider is set.'))
