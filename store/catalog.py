"""Store panel: products, flash sales, coupons, home banners and delivery charges."""
from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from orders.forms import DeliveryZoneForm
from orders.models import Coupon, DeliveryZone
from products.models import Banner, Category, FlashSale, Product

from .access import store_view
from .forms import BannerForm, CouponForm, FlashSaleForm, GalleryFormSet, ProductForm, VariantFormSet
from .views import paginate, redirect_back, render_store


# ---------- Products ----------

@store_view('products.change_product')
def product_list(request):
    products = Product.objects.select_related('category').annotate(
        variant_count=Count('variants', filter=Q(variants__is_active=True), distinct=True))
    q = request.GET.get('q', '').strip()
    if q:
        products = products.filter(Q(title__icontains=q) | Q(brand__icontains=q) | Q(variants__sku__iexact=q)).distinct()
    category = request.GET.get('category', '')
    if category.isdigit():
        products = products.filter(category_id=category)
    stock = request.GET.get('stock', '')
    if stock == 'low':
        products = products.filter(stock__gt=0, stock__lte=settings.LOW_STOCK_THRESHOLD)
    elif stock == 'out':
        products = products.filter(stock=0)
    status = request.GET.get('status', '')
    if status in ('active', 'hidden'):
        products = products.filter(is_active=status == 'active')
    return render_store(request, 'store/products/list.html', {
        'page_obj': paginate(request, products.order_by('-created_at')), 'q': q, 'categories': Category.objects.all(),
        'category': category, 'stock': stock, 'status': status, 'low_stock': settings.LOW_STOCK_THRESHOLD,
    }, section='store:products')


@store_view('products.change_product')
def product_form(request, pk=None):
    product = get_object_or_404(Product, pk=pk) if pk else None
    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    variants = VariantFormSet(request.POST or None, instance=product, prefix='variants')
    gallery = GalleryFormSet(request.POST or None, request.FILES or None, instance=product, prefix='gallery')
    if request.method == 'POST' and form.is_valid() and variants.is_valid() and gallery.is_valid():
        with transaction.atomic():
            product = form.save()
            variants.instance = gallery.instance = product
            variants.save()
            gallery.save()
        messages.success(request, f'"{product.title}" saved.')
        if 'add_another' in request.POST:
            return redirect('store:product_add')
        return redirect('store:product_edit', product.pk)
    return render_store(request, 'store/products/form.html', {
        'form': form, 'variants': variants, 'gallery': gallery, 'product': product,
    }, section='store:products')


@require_POST
@store_view('products.change_product')
def product_quick_update(request, pk):
    """Stock and visibility straight from the product list."""
    product = get_object_or_404(Product, pk=pk)
    if 'toggle_active' in request.POST:
        product.is_active = not product.is_active
        product.save(update_fields=['is_active', 'updated_at'])
        messages.success(request, f'"{product.title}" is now {"visible" if product.is_active else "hidden"}.')
    elif product.variants.filter(is_active=True).exists():
        messages.error(request, f'"{product.title}" has options; change their stock on the product page.')
    else:
        try:
            stock = int(request.POST.get('stock', ''))
            if stock < 0:
                raise ValueError
        except ValueError:
            messages.error(request, 'Stock must be a whole number, 0 or more.')
        else:
            product.stock = stock
            product.save(update_fields=['stock', 'updated_at'])
            messages.success(request, f'Stock of "{product.title}" set to {stock}.')
    return redirect_back(request, 'store:products')


# ---------- Simple sections: flash sales, coupons, banners, delivery ----------

def _simple_form(request, model, form_class, pk, section, list_url, title):
    obj = get_object_or_404(model, pk=pk) if pk else None
    form = form_class(request.POST or None, request.FILES or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        messages.success(request, f'"{obj}" saved.')
        return redirect(list_url)
    return render_store(request, 'store/form.html', {
        'form': form, 'object': obj, 'title': (f'Edit {title}' if obj else f'New {title}'), 'back_url': list_url,
    }, section=section)


@store_view('products.change_flashsale')
def flash_sale_list(request):
    now = timezone.now()
    sales = FlashSale.objects.annotate(product_count=Count('products'))
    for sale in sales:
        sale.state = ('Off' if not sale.is_active else 'Running' if sale.starts_at <= now < sale.ends_at
                      else 'Scheduled' if now < sale.starts_at else 'Ended')
    return render_store(request, 'store/flash_sales.html', {'sales': sales}, section='store:flash_sales')


@store_view('products.change_flashsale')
def flash_sale_form(request, pk=None):
    return _simple_form(request, FlashSale, FlashSaleForm, pk, 'store:flash_sales', 'store:flash_sales', 'flash sale')


@store_view('orders.change_coupon')
def coupon_list(request):
    now = timezone.now()
    coupons = Coupon.objects.select_related('user')
    show = request.GET.get('show', 'public')
    coupons = coupons.filter(user__isnull=show == 'public') if show in ('public', 'personal') else coupons
    page = paginate(request, coupons)
    for coupon in page:
        coupon.state = ('Off' if not coupon.is_active else 'Expired' if coupon.valid_to < now
                        else 'Scheduled' if coupon.valid_from > now
                        else 'Used up' if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit
                        else 'Active')
    return render_store(request, 'store/coupons.html', {'page_obj': page, 'show': show}, section='store:coupons')


@store_view('orders.change_coupon')
def coupon_form(request, pk=None):
    return _simple_form(request, Coupon, CouponForm, pk, 'store:coupons', 'store:coupons', 'coupon')


@store_view('products.change_banner')
def banner_list(request):
    return render_store(request, 'store/banners.html', {'banners': Banner.objects.all()}, section='store:banners')


@store_view('products.change_banner')
def banner_form(request, pk=None):
    return _simple_form(request, Banner, BannerForm, pk, 'store:banners', 'store:banners', 'banner')


@require_POST
@store_view('products.change_banner')
def banner_delete(request, pk):
    banner = get_object_or_404(Banner, pk=pk)
    banner.delete()
    messages.success(request, f'Banner "{banner.title}" deleted.')
    return redirect('store:banners')


@store_view('orders.change_deliveryzone')
def delivery_list(request):
    return render_store(request, 'store/delivery.html', {'zones': DeliveryZone.objects.all()},
                        section='store:delivery')


@store_view('orders.change_deliveryzone')
def delivery_form(request, pk=None):
    return _simple_form(request, DeliveryZone, DeliveryZoneForm, pk, 'store:delivery', 'store:delivery',
                        'delivery zone')
