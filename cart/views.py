from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from orders.models import Coupon
from products.models import Product

from .cart import Cart


def _is_ajax(request):
    return request.headers.get('x-requested-with') == 'XMLHttpRequest'


def _cart_json(cart, **extra):
    data = {
        'cart_count': len(cart),
        'subtotal': str(cart.get_subtotal()),
        'discount': str(cart.get_discount()),
        'total': str(cart.get_total()),
    }
    data.update(extra)
    return JsonResponse(data)


def _redirect_back(request, default='cart_summary'):
    next_url = request.POST.get('next')
    if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}, request.is_secure()):
        return redirect(next_url)
    return redirect(default)


def _parse_quantity(value, default=1):
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return default


def cart_summary(request):
    return render(request, 'cart/cart_summary.html')


@require_POST
def cart_add(request):
    cart = Cart(request)
    product = get_object_or_404(Product.objects.active(), id=request.POST.get('product_id'))
    requested = _parse_quantity(request.POST.get('quantity'))
    before = cart.quantity_of(product.id)
    new_qty = cart.add(product, requested)

    if not product.in_stock:
        msg, level = f'Sorry, "{product.title}" is out of stock.', 'error'
    elif new_qty - before < requested:
        msg, level = f'Only {product.stock} of "{product.title}" available. Your cart has {new_qty}.', 'warning'
    else:
        msg, level = f'"{product.title}" added to your cart.', 'success'

    if _is_ajax(request):
        return _cart_json(cart, message=msg, level=level)
    getattr(messages, level)(request, msg)
    return _redirect_back(request)


@require_POST
def cart_update(request):
    cart = Cart(request)
    product = get_object_or_404(Product, id=request.POST.get('product_id'))
    qty = cart.add(product, _parse_quantity(request.POST.get('quantity'), 0), override=True)
    if _is_ajax(request):
        return _cart_json(
            cart,
            product_id=product.id,
            quantity=qty,
            item_subtotal=str(product.final_price * qty),
            max_quantity=product.stock,
        )
    return redirect('cart_summary')


@require_POST
def cart_remove(request):
    cart = Cart(request)
    product_id = request.POST.get('product_id')
    cart.remove(product_id)
    if _is_ajax(request):
        return _cart_json(cart, product_id=product_id)
    return redirect('cart_summary')


@require_POST
def coupon_apply(request):
    cart = Cart(request)
    code = request.POST.get('code', '').strip()
    coupon = Coupon.objects.filter(code__iexact=code).first()
    if coupon is None:
        messages.error(request, 'Invalid coupon code.')
    else:
        ok, reason = coupon.is_valid_for(cart.get_subtotal())
        if ok:
            cart.apply_coupon(coupon)
            messages.success(request, f'Coupon "{coupon.code}" applied.')
        else:
            messages.error(request, reason)
    return _redirect_back(request)


@require_POST
def coupon_remove(request):
    Cart(request).remove_coupon()
    messages.info(request, 'Coupon removed.')
    return _redirect_back(request)
