"""Staff roles. Each role is a Django group with the permissions its store panel sections need."""
from django.contrib.auth.models import Group, Permission

ROLES = {
    'Order manager': {
        'description': 'Processes orders, returns and customer questions.',
        'perms': ['orders.change_order', 'orders.change_returnrequest', 'products.change_question',
                  'auth.view_user'],
    },
    'Catalog manager': {
        'description': 'Manages products, prices, stock, flash sales, banners and coupons.',
        'perms': ['products.change_product', 'products.change_flashsale', 'products.change_banner',
                  'orders.change_coupon', 'orders.change_deliveryzone'],
    },
}


def create_role_groups(**kwargs):
    for name, role in ROLES.items():
        group, _ = Group.objects.get_or_create(name=name)
        perms = []
        for code in role['perms']:
            app_label, codename = code.split('.')
            perm = Permission.objects.filter(content_type__app_label=app_label, codename=codename).first()
            if perm:
                perms.append(perm)
        group.permissions.set(perms)


def role_of(user):
    if user.is_superuser:
        return 'Owner'
    names = [g.name for g in user.groups.all() if g.name in ROLES]
    return ', '.join(names) or 'Staff (no role)'
