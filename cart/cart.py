from decimal import Decimal

from products.models import Product

CART_SESSION_ID = 'cart'
COUPON_SESSION_ID = 'coupon_id'


class Cart:
    """Session-backed shopping cart.

    The session only stores product ids and quantities; prices are always read
    from the database so a price change in the admin is reflected immediately.
    """

    def __init__(self, request):
        self.session = request.session
        self.cart = self.session.setdefault(CART_SESSION_ID, {})
        self._items = None

    def _save(self):
        self.session.modified = True
        self._items = None

    def add(self, product, quantity=1, override=False):
        """Add (or set, with override=True) a product's quantity, capped at stock. Returns the new quantity."""
        pid = str(product.id)
        current = 0 if override else self.cart.get(pid, {}).get('quantity', 0)
        new_qty = min(current + int(quantity), product.stock)
        if new_qty <= 0:
            self.remove(product.id)
            return 0
        self.cart[pid] = {'quantity': new_qty}
        self._save()
        return new_qty

    def remove(self, product_id):
        if self.cart.pop(str(product_id), None) is not None:
            self._save()

    def clear(self):
        self.session.pop(CART_SESSION_ID, None)
        self.session.pop(COUPON_SESSION_ID, None)
        self.cart = {}
        self._save()

    def quantity_of(self, product_id):
        return self.cart.get(str(product_id), {}).get('quantity', 0)

    def __iter__(self):
        if self._items is None:
            products = Product.objects.active().filter(id__in=self.cart.keys()).select_related('category')
            found = {str(p.id): p for p in products}
            # Drop products that were deleted or deactivated since they were added.
            for pid in list(self.cart):
                if pid not in found:
                    del self.cart[pid]
                    self.session.modified = True
            self._items = []
            for pid, data in self.cart.items():
                product = found[pid]
                qty = data['quantity']
                self._items.append({
                    'product': product,
                    'quantity': qty,
                    'price': product.final_price,
                    'subtotal': product.final_price * qty,
                    'available': qty <= product.stock,
                })
        return iter(self._items)

    def __len__(self):
        return sum(item['quantity'] for item in self.cart.values())

    def is_empty(self):
        return not self.cart

    def get_subtotal(self):
        return sum((item['subtotal'] for item in self), Decimal('0.00'))

    # Coupons

    @property
    def coupon(self):
        from orders.models import Coupon

        coupon_id = self.session.get(COUPON_SESSION_ID)
        if not coupon_id:
            return None
        coupon = Coupon.objects.filter(id=coupon_id).first()
        if coupon is None or not coupon.is_valid_for(self.get_subtotal())[0]:
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
        return self.get_subtotal() - self.get_discount()
