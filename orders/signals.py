from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Order
from .services import send_order_email


@receiver(pre_save, sender=Order)
def remember_previous_status(sender, instance, **kwargs):
    instance._previous_status = (
        Order.objects.filter(pk=instance.pk).values_list('status', flat=True).first() if instance.pk else None
    )


@receiver(post_save, sender=Order)
def email_on_status_change(sender, instance, created, **kwargs):
    previous = getattr(instance, '_previous_status', None)
    if not created and previous and previous != instance.status:
        transaction.on_commit(lambda: send_order_email(instance, 'status'))
