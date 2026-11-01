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
    area = models.CharField(max_length=100, help_text='Thana / upazila / area')
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
        return f'{self.full_name}, {self.address_line}, {self.area}, {self.district}'


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
