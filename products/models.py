from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.cache import cache
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Count, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from simple_history.models import HistoricalRecords

FLASH_SALE_CACHE_KEY = 'flash-sale-map'


def unique_slugify(instance, value, max_length):
    """Return a slug unique for the model: 'iphone-15', 'iphone-15-2', ..."""
    base = slugify(value)[:max_length - 6] or instance.__class__.__name__.lower()
    slug = base
    qs = instance.__class__.objects.exclude(pk=instance.pk)
    n = 2
    while qs.filter(slug=slug).exists():
        slug = f'{base}-{n}'
        n += 1
    return slug


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.name, 120)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('category_detail', args=[self.slug])

    def __str__(self):
        return self.name


class ProductQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def with_rating(self):
        qs = self.annotate(avg_rating=Avg('reviews__rating'), review_count=Count('reviews', distinct=True))
        # Django ignores Meta.ordering on aggregated queries, so re-apply it explicitly.
        return qs if qs.query.order_by else qs.order_by(*self.model._meta.ordering)

    def with_sold(self):
        """Annotate `sold`: units in orders that weren't cancelled (a subquery, so it can't
        double count when combined with with_rating()'s join)."""
        from orders.models import Order, OrderItem

        sold = (
            OrderItem.objects.filter(product=OuterRef('pk'))
            .exclude(order__status=Order.Status.CANCELLED)
            .values('product')
            .annotate(total=Sum('quantity'))
            .values('total')
        )
        return self.annotate(sold=Coalesce(Subquery(sold), 0))


def money(value):
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def active_flash_sales():
    """{product_id: (percent, ends_at)} for flash sales running now. Cached briefly; cleared on save."""
    data = cache.get(FLASH_SALE_CACHE_KEY)
    now = timezone.now()
    if data is None:
        data = {}
        upcoming = FlashSale.objects.filter(is_active=True, ends_at__gt=now).prefetch_related('products')
        for sale in upcoming:
            for pid in sale.products.values_list('id', flat=True):
                data.setdefault(pid, []).append((sale.starts_at, sale.ends_at, sale.discount_percent))
        cache.set(FLASH_SALE_CACHE_KEY, data, 300)
    result = {}
    for pid, windows in data.items():
        running = [(pct, end) for start, end, pct in windows if start <= now < end]
        if running:
            result[pid] = max(running)
    return result


class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    brand = models.CharField(max_length=100, blank=True)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_price = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True,
        help_text='Sale price. Leave empty to sell at the regular price.',
    )
    stock = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    is_active = models.BooleanField(default=True, help_text='Uncheck to hide the product from the shop.')
    is_featured = models.BooleanField(default=False, help_text='Show in the Featured section on the home page.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProductQuerySet.as_manager()
    history = HistoricalRecords(excluded_fields=['updated_at'])

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['is_active', 'is_featured']),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.title, 220)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('product_detail', args=[self.slug])

    @property
    def flash_sale(self):
        """(percent, ends_at) if this product is in a running flash sale, else None."""
        if not hasattr(self, '_flash_sale'):
            self._flash_sale = active_flash_sales().get(self.pk)
        return self._flash_sale

    @property
    def sale_price(self):
        """Regular sale price from the admin (ignores flash sales)."""
        if self.discount_price is not None and self.discount_price < self.price:
            return self.discount_price
        return None

    @property
    def final_price(self):
        return apply_flash_sale(self.price, self.sale_price, self.flash_sale)

    @property
    def has_discount(self):
        return self.final_price < self.price

    @property
    def discount_percent(self):
        if not self.has_discount:
            return 0
        return round((self.price - self.final_price) / self.price * 100)

    @property
    def has_variants(self):
        if not hasattr(self, '_active_variants'):
            self._active_variants = [v for v in self.variants.all() if v.is_active]
        return bool(self._active_variants)

    @property
    def active_variants(self):
        self.has_variants  # noqa: B018 - fills the cache
        return self._active_variants

    def image_url_for(self, color=''):
        """The photo of this colour if the gallery has one, else the main image (or None)."""
        if color:
            for img in self.images.all():
                if img.color == color:
                    return img.image.url
        return self.image.url if self.image else None

    @property
    def gallery(self):
        """Main image first, then the extra gallery images. A gallery with one photo per colour
        already covers the main image, so it isn't repeated."""
        extra = [{'url': img.image.url, 'alt': img.alt or self.title, 'color': img.color} for img in self.images.all()]
        if self.image and not any(img['color'] for img in extra):
            return [{'url': self.image.url, 'alt': self.title, 'color': ''}] + extra
        return extra or ([{'url': self.image.url, 'alt': self.title, 'color': ''}] if self.image else [])

    @property
    def in_stock(self):
        return self.stock > 0

    @property
    def low_stock(self):
        return 0 < self.stock <= settings.LOW_STOCK_THRESHOLD

    def __str__(self):
        return self.title


def apply_flash_sale(regular, sale, flash):
    """The lowest of the sale price and the flash-sale price (flash % off the regular price)."""
    best = sale if sale is not None else regular
    if flash:
        best = min(best, money(regular * (100 - flash[0]) / 100))
    return best


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/gallery/')
    alt = models.CharField(max_length=200, blank=True)
    color = models.CharField(max_length=40, blank=True,
                             help_text='Optional: show this image when the customer picks this colour.')
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f'{self.product} image {self.sort_order}'


class ProductVariant(models.Model):
    """A sellable option of a product (size, colour, storage) with its own stock and optional price."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    size = models.CharField(max_length=20, blank=True)
    color = models.CharField(max_length=40, blank=True)
    storage = models.CharField(max_length=20, blank=True, help_text='e.g. 128GB')
    sku = models.CharField(max_length=40, unique=True, blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True,
                                help_text="Leave empty to use the product's price.")
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(fields=['product', 'size', 'color', 'storage'], name='unique_variant_options'),
        ]

    @property
    def label(self):
        return ' / '.join(v for v in (self.color, self.size, self.storage) if v) or 'Default'

    @property
    def regular_price(self):
        return self.price if self.price is not None else self.product.price

    @property
    def sale_price(self):
        if self.price is None:
            return self.product.sale_price
        if self.discount_price is not None and self.discount_price < self.price:
            return self.discount_price
        return None

    @property
    def final_price(self):
        return apply_flash_sale(self.regular_price, self.sale_price, self.product.flash_sale)

    @property
    def in_stock(self):
        return self.stock > 0

    def __str__(self):
        return f'{self.product} - {self.label}'


class Banner(models.Model):
    """Home page hero slide, managed from the admin."""

    title = models.CharField(max_length=120)
    subtitle = models.CharField(max_length=200, blank=True)
    image = models.ImageField(upload_to='banners/')
    link_url = models.CharField(max_length=300, blank=True, help_text='e.g. /shop/?sort=price_asc')
    button_text = models.CharField(max_length=40, default='Shop now')
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(blank=True, null=True)
    ends_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['sort_order', 'id']

    @classmethod
    def live(cls):
        now = timezone.now()
        return cls.objects.filter(is_active=True).filter(
            Q(starts_at__isnull=True) | Q(starts_at__lte=now), Q(ends_at__isnull=True) | Q(ends_at__gt=now),
        )

    def __str__(self):
        return self.title


class FlashSale(models.Model):
    title = models.CharField(max_length=120, default='Flash sale')
    discount_percent = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(90)])
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField()
    products = models.ManyToManyField(Product, related_name='flash_sales')
    is_active = models.BooleanField(default=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ['-starts_at']

    @classmethod
    def current(cls):
        now = timezone.now()
        return cls.objects.filter(is_active=True, starts_at__lte=now, ends_at__gt=now).first()

    def __str__(self):
        return f'{self.title} ({self.discount_percent}% off)'


class Bundle(models.Model):
    """Buy all these products together and pay `bundle_price` instead of the sum."""

    title = models.CharField(max_length=150)
    products = models.ManyToManyField(Product, related_name='bundles')
    bundle_price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)

    def regular_total(self):
        return sum((p.final_price for p in self.products.all()), Decimal('0.00'))

    def savings(self):
        return max(self.regular_total() - self.bundle_price, Decimal('0.00'))

    def __str__(self):
        return self.title


class Question(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='questions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='questions')
    question = models.TextField(max_length=500)
    answer = models.TextField(blank=True)
    answered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='+')
    answered_at = models.DateTimeField(blank=True, null=True)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.question[:60]


class PriceAlert(models.Model):
    """'Tell me when the price drops' for one product."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='price_alerts')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='price_alerts')
    price_when_set = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    notified_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'product'], name='one_price_alert_per_product')]

    def __str__(self):
        return f'{self.user} → {self.product}'


class Review(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['product', 'user'], name='one_review_per_user_per_product'),
        ]

    def __str__(self):
        return f'{self.product} - {self.rating}★ by {self.user}'


class ReviewImage(models.Model):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='reviews/')

    def __str__(self):
        return f'Photo for {self.review}'
