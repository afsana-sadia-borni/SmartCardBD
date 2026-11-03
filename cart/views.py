from django import forms
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core.numerals import localize_digits
from core.ratelimit import hit_limit
from orders.models import Coupon
from products.models import Product, ProductVariant

from .cart import CART_EMAIL_KEY, Cart, make_key


def _is_ajax(request):
    return request.headers.get('x-requested-with') == 'XMLHttpRequest'


def _cart_json(request, cart, **extra):
    data = {
        'cart_count': len(cart),
        'cart_count_display': localize_digits(len(cart)),
        'subtotal': str(cart.get_subtotal()),
        'discount': str(cart.get_discount()),
        'bundle_discount': str(cart.get_bundle_discount()),
        'total': str(cart.get_total()),
        'mini_cart_html': render_to_string('cart/_mini_cart.html', {'cart': cart}, request=request),
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


def _get_variant(product, variant_id):
    if not variant_id:
        return None
    try:
        return ProductVariant.objects.get(pk=int(variant_id), product=product, is_active=True)
    except (ValueError, ProductVariant.DoesNotExist):
        return None


def cart_summary(request):
    return render(request, 'cart/cart_summary.html')


def mini_cart(request):
    return render(request, 'cart/_mini_cart.html')


@require_POST
def cart_add(request):
    cart = Cart(request)
    product = get_object_or_404(Product.objects.active(), id=request.POST.get('product_id'))
    variant = _get_variant(product, request.POST.get('variant_id'))
    requested = _parse_quantity(request.POST.get('quantity'))

    if product.has_variants and variant is None:
        msg, level = f'Please choose an option for "{product.title}".', 'warning'
        if _is_ajax(request):
            return _cart_json(request, cart, message=msg, level=level, added=False, needs_options=True,
                              product_url=product.get_absolute_url())
        messages.warning(request, msg)
        return redirect(product)

    name = f'{product.title} ({variant.label})' if variant else product.title
    stock = variant.stock if variant else product.stock
    before = cart.quantity_of(product.id, variant.id if variant else None)
    new_qty = cart.add(product, requested, variant=variant)
    if stock <= 0:
        msg, level = f'Sorry, "{name}" is out of stock.', 'error'
    elif new_qty - before < requested:
        msg, level = f'Only {stock} of "{name}" available. Your cart has {new_qty}.', 'warning'
    else:
        msg, level = f'"{name}" added to your cart.', 'success'

    if _is_ajax(request):
        return _cart_json(request, cart, message=msg, level=level, added=new_qty > before)
    getattr(messages, level)(request, msg)
    return _redirect_back(request)


@require_POST
def cart_update(request):
    cart = Cart(request)
    product = get_object_or_404(Product, id=request.POST.get('product_id'))
    variant = _get_variant(product, request.POST.get('variant_id'))
    qty = cart.add(product, _parse_quantity(request.POST.get('quantity'), 0), override=True, variant=variant)
    unit = variant.final_price if variant else product.final_price
    if _is_ajax(request):
        return _cart_json(
            request,
            cart,
            product_id=product.id,
            key=make_key(product.id, variant.id if variant else None),
            quantity=qty,
            item_subtotal=str(unit * qty),
            max_quantity=variant.stock if variant else product.stock,
        )
    return redirect('cart_summary')


@require_POST
def cart_remove(request):
    cart = Cart(request)
    product_id = request.POST.get('product_id')
    key = make_key(product_id, request.POST.get('variant_id') or None)
    cart.remove(key)
    if _is_ajax(request):
        return _cart_json(request, cart, product_id=product_id, key=key)
    return redirect('cart_summary')


@require_POST
def coupon_apply(request):
    cart = Cart(request)
    code = request.POST.get('code', '').strip()
    coupon = Coupon.objects.filter(code__iexact=code).first()
    if coupon is None:
        messages.error(request, 'Invalid coupon code.')
    else:
        ok, reason = coupon.is_valid_for(cart.get_subtotal(), request.user)
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


@require_POST
def remember_email(request):
    """A guest typed their email at checkout: keep it with the cart so we can send one reminder
    if they don't finish the order."""
    field = forms.EmailField()
    try:
        email = field.clean(request.POST.get('email', '').strip())
    except forms.ValidationError:
        return JsonResponse({'ok': False}, status=400)
    if request.user.is_authenticated or hit_limit(request, 'cart-email', limit=20, window_seconds=600):
        return JsonResponse({'ok': False}, status=400)
    request.session[CART_EMAIL_KEY] = email.lower()
    return JsonResponse({'ok': True})
