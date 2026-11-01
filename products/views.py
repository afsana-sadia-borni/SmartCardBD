from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import Wishlist
from orders.models import Order, OrderItem
from recommendations.engine import bought_together, similar_products

from .forms import ReviewForm
from .models import Category, Product

PRODUCTS_PER_PAGE = 12

SORT_OPTIONS = {
    'newest': ('Newest', ['-created_at']),
    'price_asc': ('Price: Low to High', ['effective_price', '-created_at']),
    'price_desc': ('Price: High to Low', ['-effective_price', '-created_at']),
    'rating': ('Top Rated', [F('avg_rating').desc(nulls_last=True), '-review_count', '-created_at']),
}


def home(request):
    base = Product.objects.active().with_rating().select_related('category')
    featured = list(base.filter(is_featured=True)[:8])
    return render(request, 'products/home.html', {
        'featured_products': featured or list(base[:8]),
        'latest_products': base[:8] if featured else [],
        'deals': base.filter(discount_price__isnull=False)[:4],
    })


def product_list(request, category_slug=None):
    category = get_object_or_404(Category, slug=category_slug) if category_slug else None
    products = (
        Product.objects.active()
        .with_rating()
        .select_related('category')
        .annotate(effective_price=Coalesce('discount_price', 'price'))
    )
    if category:
        products = products.filter(category=category)

    q = request.GET.get('q', '').strip()
    if q:
        products = products.filter(
            Q(title__icontains=q) | Q(description__icontains=q)
            | Q(brand__icontains=q) | Q(category__name__icontains=q)
        )

    def price_param(name):
        try:
            return max(float(request.GET[name]), 0)
        except (KeyError, ValueError):
            return None

    min_price, max_price = price_param('min_price'), price_param('max_price')
    if min_price is not None:
        products = products.filter(effective_price__gte=min_price)
    if max_price is not None:
        products = products.filter(effective_price__lte=max_price)

    brand = request.GET.get('brand', '').strip()
    if brand:
        products = products.filter(brand__iexact=brand)
    if request.GET.get('in_stock'):
        products = products.filter(stock__gt=0)

    sort = request.GET.get('sort', 'newest')
    if sort not in SORT_OPTIONS:
        sort = 'newest'
    products = products.order_by(*SORT_OPTIONS[sort][1])

    page = Paginator(products, PRODUCTS_PER_PAGE).get_page(request.GET.get('page'))

    brands_qs = Product.objects.active().exclude(brand='')
    if category:
        brands_qs = brands_qs.filter(category=category)

    return render(request, 'products/product_list.html', {
        'category': category,
        'page_obj': page,
        'products': page.object_list,
        'q': q,
        'sort': sort,
        'sort_options': {k: v[0] for k, v in SORT_OPTIONS.items()},
        'brands': brands_qs.order_by('brand').values_list('brand', flat=True).distinct(),
        'selected_brand': brand,
        'min_price': request.GET.get('min_price', ''),
        'max_price': request.GET.get('max_price', ''),
        'in_stock': bool(request.GET.get('in_stock')),
    })


def _can_review(user, product):
    return user.is_authenticated and OrderItem.objects.filter(
        order__user=user, order__status=Order.Status.DELIVERED, product=product,
    ).exists()


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.active().with_rating().select_related('category'), slug=slug,
    )
    reviews = product.reviews.select_related('user')
    user = request.user
    user_review = reviews.filter(user=user).first() if user.is_authenticated else None

    return render(request, 'products/product_detail.html', {
        'product': product,
        'reviews': reviews,
        'can_review': _can_review(user, product),
        'review_form': ReviewForm(instance=user_review),
        'user_review': user_review,
        'in_wishlist': user.is_authenticated and Wishlist.objects.filter(user=user, product=product).exists(),
        'similar_products': similar_products(product),
        'bought_together': bought_together(product),
    })


def product_detail_by_id(request, pk):
    """Old /product/<id>/ links permanently redirect to the slug URL."""
    product = get_object_or_404(Product.objects.active(), pk=pk)
    return redirect(product, permanent=True)


@login_required
@require_POST
def add_review(request, slug):
    product = get_object_or_404(Product.objects.active(), slug=slug)
    if not _can_review(request.user, product):
        messages.error(request, 'You can review a product after it has been delivered to you.')
        return redirect(product)

    existing = product.reviews.filter(user=request.user).first()
    form = ReviewForm(request.POST, instance=existing)
    if form.is_valid():
        review = form.save(commit=False)
        review.product = product
        review.user = request.user
        review.save()
        messages.success(request, 'Thanks! Your review has been saved.')
    else:
        messages.error(request, 'Please choose a rating between 1 and 5.')
    return redirect(f'{product.get_absolute_url()}#reviews')
