from django.core.management.base import BaseCommand

from products.services import send_due_price_alerts


class Command(BaseCommand):
    help = ('Notify customers whose watched products got cheaper (catches flash sales that start on schedule). '
            'Celery beat runs this every 15 minutes; without Celery, run it from cron.')

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(f'Sent {send_due_price_alerts()} price-drop alert(s).'))
