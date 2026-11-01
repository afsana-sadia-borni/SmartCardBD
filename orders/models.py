import secrets
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from accounts.constants import DISTRICT_CHOICES
from accounts.models import phone_validator


class Coupon(models.Model):
    PERCENT = 'percent'
    FLAT = 'flat'
    TYPE_CHOICES = [(PERCENT, 'Percentage (%)'), (FLAT, 'Flat amount (৳)')]

    code = models.CharField(max_length=30, unique=True)
    discount_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default=PERCENT)
    value = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    max_discount = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True,
        help_text='Upper limit for percentage coupons (optional).',
    )
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_to = models.DateTimeField()
    usage_limit = models.PositiveIntegerField(blank=True, null=True, help_text='Empty = unlimited.')
    used_count = models.PositiveIntegerField(default=0, editable=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-valid_to']

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def is_valid_for(self, subtotal):
        """Return (is_valid, reason)."""
        now = timezone.now()
        if not self.is_active:
            return False, 'This coupon is no longer active.'
        if now < self.valid_from:
            return False, 'This coupon is not active yet.'
        if now > self.valid_to:
            return False, 'This coupon has expired.'
        if self.usage_limit is not None and self.used_count >= self.usage_limit:
            return False, 'This coupon has reached its usage limit.'
        if subtotal < self.min_order_amount:
            return False, f'Minimum order amount for this coupon is ৳{self.min_order_amount:,.0f}.'
        return True, ''

    def calculate_discount(self, subtotal):
        if self.discount_type == self.PERCENT:
            discount = (subtotal * self.value / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if self.max_discount is not None:
                discount = min(discount, self.max_discount)
        else:
            discount = self.value
        return min(discount, subtotal)

    def __str__(self):
        return self.code


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        SHIPPED = 'shipped', 'Shipped'
        DELIVERED = 'delivered', 'Delivered'
        CANCELLED = 'cancelled', 'Cancelled'

    class PaymentMethod(models.TextChoices):
        COD = 'cod', 'Cash on Delivery'
        SSLCOMMERZ = 'sslcommerz', 'Online Payment (bKash, Nagad, Card)'

    class PaymentStatus(models.TextChoices):
        UNPAID = 'unpaid', 'Unpaid'
        PAID = 'paid', 'Paid'
        FAILED = 'failed', 'Failed'

    STATUS_FLOW = [Status.PENDING, Status.CONFIRMED, Status.SHIPPED, Status.DELIVERED]

    order_number = models.CharField(max_length=20, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders',
    )

    # Shipping details are copied onto the order so later address edits don't change history.
    full_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=15, validators=[phone_validator])
    district = models.CharField(max_length=50, choices=DISTRICT_CHOICES)
    area = models.CharField(max_length=100)
    address_line = models.CharField(max_length=255)
    note = models.TextField(blank=True)

    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipping_cost = models.DecimalField(max_digits=8, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)

    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.COD)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)
    transaction_id = models.CharField(max_length=100, blank=True, help_text='Gateway validation / bank transaction id')

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', '-created_at'])]

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self._generate_order_number()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_order_number():
        prefix = timezone.localdate().strftime('SCB%y%m%d')
        while True:
            number = f'{prefix}-{secrets.token_hex(3).upper()}'
            if not Order.objects.filter(order_number=number).exists():
                return number

    def get_absolute_url(self):
        return reverse('order_detail', args=[self.order_number])

    @property
    def can_cancel(self):
        return self.status == self.Status.PENDING and self.payment_status != self.PaymentStatus.PAID

    @property
    def can_pay_online(self):
        return (
            self.payment_method == self.PaymentMethod.SSLCOMMERZ
            and self.payment_status != self.PaymentStatus.PAID
            and self.status == self.Status.PENDING
        )

    @property
    def progress_steps(self):
        """For the tracking timeline: [(label, done), ...]."""
        if self.status == self.Status.CANCELLED:
            return []
        current = self.STATUS_FLOW.index(self.status)
        return [(step.label, i <= current) for i, step in enumerate(self.STATUS_FLOW)]

    @property
    def item_count(self):
        return sum(item.quantity for item in self.items.all())

    def __str__(self):
        return self.order_number


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('products.Product', on_delete=models.SET_NULL, null=True, related_name='order_items')
    # Snapshot of the product at purchase time.
    product_title = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()

    @property
    def subtotal(self):
        return self.price * self.quantity

    def __str__(self):
        return f'{self.quantity} × {self.product_title}'
