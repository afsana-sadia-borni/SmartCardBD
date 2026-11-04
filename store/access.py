from functools import wraps

from django.core.exceptions import PermissionDenied
from django.http import Http404

# (url name, label, icon, permission needed or None). Sections a staff member can't use are hidden.
NAV = [
    ('Overview', [
        ('store:dashboard', 'Dashboard', 'speedometer2', None),
        ('store:reports', 'Reports', 'bar-chart-line', 'orders.change_order'),
    ]),
    ('Sales', [
        ('store:orders', 'Orders', 'bag-check', 'orders.change_order'),
        ('store:returns', 'Returns', 'arrow-return-left', 'orders.change_returnrequest'),
        ('store:questions', 'Questions', 'chat-left-dots', 'products.change_question'),
        ('store:customers', 'Customers', 'people', 'auth.view_user'),
    ]),
    ('Catalog', [
        ('store:products', 'Products', 'box-seam', 'products.change_product'),
        ('store:flash_sales', 'Flash sales', 'lightning-charge', 'products.change_flashsale'),
        ('store:coupons', 'Coupons', 'ticket-perforated', 'orders.change_coupon'),
        ('store:banners', 'Home banners', 'images', 'products.change_banner'),
    ]),
    ('Settings', [
        ('store:delivery', 'Delivery charges', 'truck', 'orders.change_deliveryzone'),
        ('store:team', 'Team', 'person-badge', 'superuser'),
        ('store:integrations', 'Integrations', 'plug', 'superuser'),
    ]),
]


def can(user, perm):
    if perm is None:
        return user.is_staff
    if perm == 'superuser':
        return user.is_superuser
    return user.is_staff and user.has_perm(perm)


def store_view(perm=None):
    """Staff only; with `perm`, also that permission ('superuser' for owner-only pages).

    Visitors and customers get a plain 404, so the panel's existence isn't advertised. Staff log in on the
    normal login page and are taken to the panel.
    """
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not (request.user.is_authenticated and request.user.is_staff):
                raise Http404
            if not can(request.user, perm):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapper
    return decorator
