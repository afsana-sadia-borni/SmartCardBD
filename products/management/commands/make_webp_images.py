from django.core.management.base import BaseCommand

from products.images import make_webp_variants
from products.models import Banner, Product, ProductImage, ReviewImage


class Command(BaseCommand):
    help = 'Create the small WebP copies of every uploaded image (new uploads get them automatically).'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Rebuild copies that already exist.')

    def handle(self, *args, force, **options):
        names = set()
        for model in (Product, ProductImage, Banner, ReviewImage):
            names.update(n for n in model.objects.exclude(image='').exclude(image__isnull=True)
                         .values_list('image', flat=True) if n)
        written = sum(make_webp_variants(name, force=force) for name in sorted(names))
        self.stdout.write(self.style.SUCCESS(f'Checked {len(names)} image(s), wrote {written} WebP file(s).'))
