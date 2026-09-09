from decimal import Decimal
from products.models import Product

class Cart:
    def delete(self, product):
        product_id = str(product)
        if product_id in self.cart:
            del self.cart[product_id]
            self.session.modified = True

    def update(self, product, quantity):
        product_id = str(product)
        product_qty = int(quantity)
        ourcart = self.cart
        ourcart[product_id]['quantity'] = product_qty
        self.session.modified = True

    def __init__(self, request):
        self.session = request.session
        cart = self.session.get('session_key')
        if 'session_key' not in request.session:
            cart = self.session['session_key'] = {}
        self.cart = cart

    def add(self, product, quantity=1):
        product_id = str(product.id)
        if product_id in self.cart:
            self.cart[product_id]['quantity'] += quantity
        else:
            self.cart[product_id] = {'price': str(product.price), 'quantity': quantity}
        self.session.modified = True

    def __len__(self):
        return sum(item['quantity'] for item in self.cart.values())

    def get_prods(self):
        product_ids = self.cart.keys()
        products = Product.objects.filter(id__in=product_ids)
        return products

    def get_quants(self):
        return self.cart

    def get_total(self):
        product_ids = self.cart.keys()
        products = Product.objects.filter(id__in=product_ids)
        total = Decimal('0.00')
        for key, value in self.cart.items():
            key = int(key)
            for product in products:
                if product.id == key:
                    total += product.price * value['quantity']
        return total