import secrets

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models, transaction

from .constants import BD_PHONE_REGEX, DISTRICT_CHOICES

phone_validator = RegexValidator(BD_PHONE_REGEX, 'Enter a valid Bangladeshi mobile number, e.g. 01712345678.')


class Address(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='addresses')
    full_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15, validators=[phone_validator])
    district = models.CharField(max_length=50, choices=DISTRICT_CHOICES)
    upazila = models.CharField(max_length=60, blank=True)
    area = models.CharField(max_length=100, help_text='Area / locality')
    address_line = models.CharField(max_length=255, help_text='House, road, village')
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Addresses'
        ordering = ['-is_default', '-created_at']

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.is_default:
                Address.objects.filter(user=self.user, is_default=True).exclude(pk=self.pk).update(is_default=False)
            elif not Address.objects.filter(user=self.user).exclude(pk=self.pk).exists():
                # A user's first address is always the default.
                self.is_default = True
            super().save(*args, **kwargs)

    def __str__(self):
        parts = [self.address_line, self.area, self.upazila, self.district]
        return f'{self.full_name}, ' + ', '.join(p for p in parts if p)


class Wishlist(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wishlist')
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='wishlisted_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'product'], name='unique_wishlist_item'),
        ]

    def __str__(self):
        return f'{self.user} ♥ {self.product}'


def generate_referral_code():
    while True:
        code = 'SCB' + secrets.token_hex(3).upper()
        if not CustomerProfile.objects.filter(referral_code=code).exists():
            return code


class CustomerProfile(models.Model):
    """Loyalty data for a customer: reward points and referral."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    points = models.PositiveIntegerField(default=0)
    referral_code = models.CharField(max_length=20, unique=True)
    referred_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='referrals')
    referral_rewarded = models.BooleanField(default=False)
    # Mobile number for logging in (01XXXXXXXXX). Not verified by SMS yet (no SMS gateway).
    phone = models.CharField(max_length=11, unique=True, null=True, blank=True)
    phone_verified = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = generate_referral_code()
        super().save(*args, **kwargs)

    @property
    def points_value(self):
        """Taka value of the redeemable points."""
        blocks = self.points // settings.POINTS_REDEEM_BLOCK
        return blocks * settings.POINTS_REDEEM_VALUE

    def __str__(self):
        return f'{self.user} ({self.points} pts)'


def get_profile(user):
    profile, _ = CustomerProfile.objects.get_or_create(user=user)
    return profile


class PointTransaction(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='point_transactions')
    points = models.IntegerField(help_text='Positive = earned, negative = spent')
    reason = models.CharField(max_length=120)
    order = models.ForeignKey('orders.Order', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.points:+d} {self.reason}'


class PushSubscription(models.Model):
    """A browser that agreed to receive push notifications (Web Push API) for this user."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='push_subscriptions')
    endpoint = models.URLField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def as_subscription_info(self):
        return {'endpoint': self.endpoint, 'keys': {'p256dh': self.p256dh, 'auth': self.auth}}

    def __str__(self):
        return f'Push for {self.user}'


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    message = models.CharField(max_length=255)
    url = models.CharField(max_length=300, blank=True)
    icon = models.CharField(max_length=30, default='bell')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'is_read'])]

    def __str__(self):
        return self.message


class Subscriber(models.Model):
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    token = models.CharField(max_length=32, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(24)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email
