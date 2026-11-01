from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand

from orders.services import release_unpaid_orders


class Command(BaseCommand):
    help = 'Cancel online-payment orders that stayed unpaid too long and put their items back in stock.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--minutes', type=int, default=settings.UNPAID_ORDER_TIMEOUT_MINUTES,
            help='Age after which an unpaid order is released (default: UNPAID_ORDER_TIMEOUT_MINUTES).',
        )

    def handle(self, *args, minutes, **options):
        count = release_unpaid_orders(timedelta(minutes=minutes))
        self.stdout.write(self.style.SUCCESS(f'Released {count} unpaid order(s).'))
