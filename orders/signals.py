from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from accounts.services import award_order_points, notify, reward_referral

from .models import Order, ReturnRequest
from .services import queue_order_email

STATUS_MESSAGES = {
    Order.Status.CONFIRMED: ('Your order {n} is confirmed.', 'check2-circle'),
    Order.Status.SHIPPED: ('Your order {n} has been shipped and is on the way!', 'truck'),
    Order.Status.DELIVERED: ('Your order {n} was delivered. Enjoy!', 'box-seam'),
    Order.Status.CANCELLED: ('Your order {n} was cancelled.', 'x-circle'),
}


@receiver(pre_save, sender=Order)
def remember_previous_status(sender, instance, **kwargs):
    instance._previous_status = (
        Order.objects.filter(pk=instance.pk).values_list('status', flat=True).first() if instance.pk else None
    )


@receiver(post_save, sender=Order)
def on_status_change(sender, instance, created, **kwargs):
    previous = getattr(instance, '_previous_status', None)
    if created or not previous or previous == instance.status:
        return
    queue_order_email(instance, 'status')
    if instance.status in STATUS_MESSAGES:
        text, icon = STATUS_MESSAGES[instance.status]
        notify(instance.user, text.format(n=instance.order_number), url=instance.get_absolute_url(), icon=icon)
    if instance.status == Order.Status.DELIVERED:
        if instance.payment_method == Order.PaymentMethod.COD and instance.payment_status != Order.PaymentStatus.PAID:
            # The courier collected the cash. Done here so it holds however the order was marked delivered.
            Order.objects.filter(pk=instance.pk).update(payment_status=Order.PaymentStatus.PAID)
            instance.payment_status = Order.PaymentStatus.PAID
        award_order_points(instance)
        reward_referral(instance)


@receiver(pre_save, sender=ReturnRequest)
def remember_return_status(sender, instance, **kwargs):
    instance._previous_status = (
        ReturnRequest.objects.filter(pk=instance.pk).values_list('status', flat=True).first() if instance.pk else None
    )


@receiver(post_save, sender=ReturnRequest)
def notify_return_decision(sender, instance, created, **kwargs):
    previous = getattr(instance, '_previous_status', None)
    if created or previous == instance.status:
        return
    order = instance.order
    text = f'Your return request for order {order.order_number} is now: {instance.get_status_display()}.'
    if instance.admin_note:
        text += f' {instance.admin_note}'
    notify(order.user, text, url=order.get_absolute_url(), icon='arrow-return-left',
           email_subject=f'Return request update - {order.order_number}')
