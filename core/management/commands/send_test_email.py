from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Send a test email, to check the SMTP settings (EMAIL_HOST, EMAIL_HOST_USER, ...) in .env.'

    def add_arguments(self, parser):
        parser.add_argument('to', help='Address to send the test email to.')

    def handle(self, *args, to, **options):
        backend = settings.EMAIL_BACKEND.rsplit('.', 2)[-2]
        try:
            send_mail(f'{settings.SITE_NAME} test email', 'If you can read this, email sending works.', None, [to])
        except Exception as exc:  # noqa: BLE001 - show any SMTP problem to the person running the command
            raise CommandError(f'Sending failed: {exc}') from exc
        where = 'printed above (no EMAIL_HOST set)' if backend == 'console' else f'sent via {settings.EMAIL_HOST}'
        self.stdout.write(self.style.SUCCESS(f'Test email {where}.'))
