from decimal import Decimal

from django.db import migrations

DHAKA_SUBURBS = ['Gazipur', 'Narayanganj', 'Munshiganj', 'Manikganj', 'Narsingdi']


def create_zones(apps, schema_editor):
    DeliveryZone = apps.get_model('orders', 'DeliveryZone')
    if DeliveryZone.objects.exists():
        return
    DeliveryZone.objects.create(name='Inside Dhaka', charge=Decimal('60'), min_days=1, max_days=2,
                                districts=['Dhaka'], sort_order=1)
    DeliveryZone.objects.create(name='Dhaka suburbs', charge=Decimal('100'), min_days=2, max_days=3,
                                districts=DHAKA_SUBURBS, sort_order=2)
    DeliveryZone.objects.create(name='Outside Dhaka', charge=Decimal('120'), min_days=3, max_days=5,
                                districts=[], is_default=True, sort_order=3)


def create_profiles(apps, schema_editor):
    """Existing customers get a loyalty profile (with a referral code)."""
    import secrets

    User = apps.get_model('auth', 'User')
    CustomerProfile = apps.get_model('accounts', 'CustomerProfile')
    used = set(CustomerProfile.objects.values_list('referral_code', flat=True))
    for user in User.objects.filter(profile__isnull=True):
        code = 'SCB' + secrets.token_hex(3).upper()
        while code in used:
            code = 'SCB' + secrets.token_hex(3).upper()
        used.add(code)
        CustomerProfile.objects.create(user=user, referral_code=code)


class Migration(migrations.Migration):
    dependencies = [
        ('orders', '0002_deliveryzone_coupon_user_order_bundle_discount_and_more'),
        ('accounts', '0002_subscriber_address_upazila_alter_address_area_and_more'),
    ]

    operations = [
        migrations.RunPython(create_zones, migrations.RunPython.noop),
        migrations.RunPython(create_profiles, migrations.RunPython.noop),
    ]
