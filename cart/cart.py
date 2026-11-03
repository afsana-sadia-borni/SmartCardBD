from decimal import Decimal

from django.utils import timezone

from products.bundles import bundle_discount
from products.models import Product, ProductVariant

CART_SESSION_ID = 'cart'
COUPON_SESSION_ID = 'coupon_id'
# For abandoned-cart reminders: when the cart last changed, and whether we already sent one.
CART_UPDATED_KEY = 'cart_updated_at'
CART_REMINDED_KEY = 'cart_reminded'
# A guest's email from the checkout form, so guests can get a reminder too.
CART_EMAIL_KEY = 'cart_email'


def make_key(product_id, variant_id=None):
    return f'{product_id}:{variant_id}' if variant_id else str(product_id)


def parse_key(key):
    """'12' -> (12, None); '12:5' -> (12, 5)."""
    product_id, _, variant_id = str(key).partition(':')
    return int(product_id), int(variant_id) if variant_id else None


class Cart:
    """Session-backed shopping cart.

    The session only stores ids and quantities, keyed by product ('12') or product variant ('12:5').
    Prices are always read from the database, so price changes in the admin apply immediately.
    """

    def __init__(self, request):
        self.session = request.session
        self.user = getattr(request, 'user', None)
        self.cart = self.session.setdefault(CART_SESSION_ID, {})
        self._items = None

    def _save(self):
        self.session[CART_UPDATED_KEY] = timezone.now().isoformat()
        self.session.pop(CART_REMINDED_KEY, None)
        self.session.modified = True
        self._items = None

    def add(self, product, quantity=1, override=False, variant=None):
        """Add (or set, with override=True) a quantity, capped at stock. Returns the new quantity."""
        key = make_key(product.id, variant.id if variant else None)
        stock = variant.stock if variant else product.stock
        current = 0 if override else self.cart.get(key, {}).get('quantity', 0)
        new_qty = min(current + int(quantity), stock)
        if new_qty <= 0:
            self.remove(key)
            return 0
        self.cart[key] = {'quantity': new_qty}
        self._save()
        return new_qty

    def remove(self, key):
        if self.cart.pop(str(key), None) is not None:
            self._save()

    def clear(self):
        self.session.pop(CART_SESSION_ID, None)
        self.session.pop(COUPON_SESSION_ID, None)
        self.cart = {}
        self._save()

    def quantity_of(self, product_id, variant_id=None):
        return self.cart.get(make_key(product_id, variant_id), {}).get('quantity', 0)

    def __iter__(self):
        if self._items is None:
            keys = {key: parse_key(key) for key in self.cart}
            products = {
                p.id: p for p in Product.objects.active().filter(id__in={pid for pid, _ in keys.values()})
                .select_related('category').prefetch_related('variants', 'images')
            }
            variants = {
                v.id: v for v in ProductVariant.objects.filter(
                    id__in={vid for _, vid in keys.values() if vid}, is_active=True,
                )
            }
            self._items = []
            for key, (pid, vid) in keys.items():
                product = products.get(pid)
                variant = variants.get(vid) if vid else None
                # Drop items whose product/variant was deleted or deactivated since it was added.
                if product is None or (vid and (variant is None or variant.product_id != pid)):
                    del self.cart[key]
                    self.session.modified = True
                    continue
                if variant:
                    variant.product = product  # share the prefetched product (and its flash-sale lookup)
                qty = self.cart[key]['quantity']
                unit = variant.final_price if variant else product.final_price
                stock = variant.stock if variant else product.stock
                self._items.append({
                    'key': key,
                    'product': product,
                    'variant': variant,
                    'image_url': product.image_url_for(variant.color if variant else ''),
                    'quantity': qty,
                    'price': unit,
                    'regular_price': variant.regular_price if variant else product.price,
                    'stock': stock,
                    'subtotal': unit * qty,
                    'available': qty <= stock,
                })
        return iter(self._items)

    def __len__(self):
        return sum(item['quantity'] for item in self.cart.values())

    def is_empty(self):
        return not self.cart

    def get_subtotal(self):
        return sum((item['subtotal'] for item in self), Decimal('0.00'))

    # Bundles

    def bundle_savings(self):
        qty, price = {}, {}
        for item in self:
            pid = item['product'].id
            qty[pid] = qty.get(pid, 0) + item['quantity']
            price[pid] = min(price.get(pid, item['price']), item['price'])
        return bundle_discount(qty, price)

    def get_bundle_discount(self):
        return self.bundle_savings()[0]

    # Coupons

    @property
    def coupon(self):
        from orders.models import Coupon

        coupon_id = self.session.get(COUPON_SESSION_ID)
        if not coupon_id:
            return None
        coupon = Coupon.objects.filter(id=coupon_id).first()
        if coupon is None or not coupon.is_valid_for(self.get_subtotal(), self.user)[0]:
            return None
        return coupon

    def apply_coupon(self, coupon):
        self.session[COUPON_SESSION_ID] = coupon.id
        self.session.modified = True

    def remove_coupon(self):
        self.session.pop(COUPON_SESSION_ID, None)
        self.session.modified = True

    def get_discount(self):
        coupon = self.coupon
        return coupon.calculate_discount(self.get_subtotal()) if coupon else Decimal('0.00')

    def get_total(self):
        return max(self.get_subtotal() - self.get_discount() - self.get_bundle_discount(), Decimal('0.00'))
