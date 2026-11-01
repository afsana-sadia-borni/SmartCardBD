from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Count
from django.urls import reverse
from django.utils.text import slugify


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
    def has_discount(self):
        return self.discount_price is not None and self.discount_price < self.price

    @property
    def final_price(self):
        return self.discount_price if self.has_discount else self.price

    @property
    def discount_percent(self):
        if not self.has_discount:
            return 0
        return round((self.price - self.discount_price) / self.price * 100)

    @property
    def in_stock(self):
        return self.stock > 0

    @property
    def low_stock(self):
        return 0 < self.stock <= settings.LOW_STOCK_THRESHOLD

    def __str__(self):
        return self.title


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
