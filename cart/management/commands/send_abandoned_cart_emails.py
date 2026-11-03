from django.core.management.base import BaseCommand

from cart.services import send_abandoned_cart_reminders


class Command(BaseCommand):
    help = ('Email customers who left items in their cart: logged-in users, and guests who typed their '
            'email at checkout. Celery beat runs this hourly; without Celery, run it from cron.')

    def add_arguments(self, parser):
        parser.add_argument('--hours', type=int, default=24, help='How long a cart must sit untouched.')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, hours, dry_run, **options):
        sent = send_abandoned_cart_reminders(hours, dry_run)
        self.stdout.write(self.style.SUCCESS(f'{"Would send" if dry_run else "Sent"} {sent} reminder(s).'))
