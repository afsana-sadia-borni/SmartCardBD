from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import F, Prefetch, Q
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.views.decorators.http import require_POST

from accounts.models import Wishlist
from core.ratelimit import hit_limit
from orders.models import Order, OrderItem
from recommendations.engine import bought_together, similar_products

from .forms import QuestionForm, ReviewForm
from .models import Banner, Bundle, Category, FlashSale, PriceAlert, Product, Question, ReviewImage
from .templatetags.shop_tags import taka

COMPARE_SESSION_KEY = 'compare'
COMPARE_MAX = 4
MAX_REVIEW_PHOTOS = 3
MAX_PHOTO_BYTES = 5 * 1024 * 1024


def _is_ajax(request):
    return request.headers.get('x-requested-with') == 'XMLHttpRequest'


def shop_products():
    """Active products with what product cards need (rating, units sold, variants) loaded up front."""
    return (
        Product.objects.active().with_rating().with_sold().select_related('category').prefetch_related('variants')
    )

PRODUCTS_PER_PAGE = 12

SORT_OPTIONS = {
    'newest': ('Newest', ['-created_at']),
    'price_asc': ('Price: Low to High', ['effective_price', '-created_at']),
    'price_desc': ('Price: High to Low', ['-effective_price', '-created_at']),
    'rating': ('Top Rated', [F('avg_rating').desc(nulls_last=True), '-review_count', '-created_at']),
}


def home(request):
    base = shop_products()
    featured = list(base.filter(is_featured=True)[:8])
    flash_sale = FlashSale.current()
    return render(request, 'products/home.html', {
        'banners': Banner.live(),
        'flash_sale': flash_sale,
        'flash_products': base.filter(flash_sales=flash_sale)[:8] if flash_sale else [],
        'featured_products': featured or list(base[:8]),
        'latest_products': base[:8] if featured else [],
        'deals': base.filter(discount_price__isnull=False)[:4],
    })


def product_list(request, category_slug=None):
    category = get_object_or_404(Category, slug=category_slug) if category_slug else None
    products = shop_products().annotate(effective_price=Coalesce('discount_price', 'price'))
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

    if request.GET.get('partial'):
        # Infinite scroll: just the next page of cards.
        html = render_to_string('products/_product_grid_items.html', {'products': page.object_list}, request=request)
        next_url = None
        if page.has_next():
            params = request.GET.copy()
            params['page'] = page.next_page_number()
            next_url = f'{request.path}?{params.urlencode()}'
        return JsonResponse({'html': html, 'next_url': next_url})

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


def _variant_data(product):
    """Variant info for the option picker on the product page."""
    variants = []
    for v in product.active_variants:
        variants.append({
            'id': v.id, 'color': v.color, 'size': v.size, 'storage': v.storage, 'label': v.label,
            'price': str(v.final_price), 'price_display': taka(v.final_price),
            'regular': str(v.regular_price), 'regular_display': taka(v.regular_price), 'stock': v.stock,
        })
    options = {}
    for attr in ('color', 'size', 'storage'):
        values = []
        for v in variants:
            if v[attr] and v[attr] not in values:
                values.append(v[attr])
        if values:
            options[attr] = values
    return variants, options


def _product_context(request, product):
    user = request.user
    variants, options = _variant_data(product)
    return {
        'product': product,
        'variants': variants,
        'variant_options': options,
        'in_wishlist': user.is_authenticated and Wishlist.objects.filter(user=user, product=product).exists(),
        'in_compare': product.id in request.session.get(COMPARE_SESSION_KEY, []),
    }


def product_detail(request, slug):
    product = get_object_or_404(
        shop_products().prefetch_related('images'), slug=slug,
    )
    reviews = product.reviews.select_related('user').prefetch_related('images')
    user = request.user
    user_review = reviews.filter(user=user).first() if user.is_authenticated else None
    questions = product.questions.select_related('user').filter(
        Q(is_published=True, answered_at__isnull=False) | Q(user_id=user.id if user.is_authenticated else None)
    )
    bundles = (
        Bundle.objects.filter(is_active=True, products=product)
        .prefetch_related(Prefetch('products', queryset=Product.objects.active()))
    )
    context = _product_context(request, product)
    context.update({
        'reviews': reviews,
        'can_review': _can_review(user, product),
        'review_form': ReviewForm(instance=user_review),
        'user_review': user_review,
        'questions': questions,
        'question_form': QuestionForm(),
        'bundles': [b for b in bundles if len(b.products.all()) > 1 and b.savings() > 0],
        'has_price_alert': user.is_authenticated and PriceAlert.objects.filter(
            user=user, product=product, notified_at__isnull=True).exists(),
        'similar_products': similar_products(product),
        'bought_together': bought_together(product),
    })
    return render(request, 'products/product_detail.html', context)


def quick_view(request, slug):
    product = get_object_or_404(shop_products().prefetch_related('images'), slug=slug)
    return render(request, 'products/_quick_view.html', _product_context(request, product))


def search_suggest(request):
    q = request.GET.get('q', '').strip()
    results = []
    if len(q) >= 2:
        products = (
            Product.objects.active().select_related('category')
            .filter(Q(title__icontains=q) | Q(brand__icontains=q) | Q(category__name__icontains=q))
            .order_by('-is_featured', '-created_at')[:5]
        )
        for p in products:
            results.append({
                'title': p.title,
                'subtitle': p.brand or p.category.name,
                'url': p.get_absolute_url(),
                'image': p.image.url if p.image else static('img/no-image.svg'),
                'price': taka(p.final_price),
                'regular': taka(p.price) if p.has_discount else '',
            })
    return JsonResponse({'query': q, 'results': results})


@require_POST
def compare_toggle(request, product_id):
    product = get_object_or_404(Product.objects.active(), pk=product_id)
    ids = [i for i in request.session.get(COMPARE_SESSION_KEY, []) if i != product.id]
    added = product.id not in request.session.get(COMPARE_SESSION_KEY, [])
    message = ''
    if added:
        if len(ids) >= COMPARE_MAX:
            ids = ids[1:]
            message = f'You can compare up to {COMPARE_MAX} products, so the oldest one was removed.'
        ids.append(product.id)
    request.session[COMPARE_SESSION_KEY] = ids
    if _is_ajax(request):
        return JsonResponse({'in_compare': added, 'count': len(ids), 'message': message})
    return redirect('compare')


def compare(request):
    ids = request.session.get(COMPARE_SESSION_KEY, [])
    found = {p.id: p for p in shop_products().filter(id__in=ids)}
    products = [found[i] for i in ids if i in found]
    return render(request, 'products/compare.html', {'products': products})


@require_POST
def compare_clear(request):
    request.session[COMPARE_SESSION_KEY] = []
    return redirect('compare')


@require_POST
def price_alert_toggle(request, product_id):
    if not request.user.is_authenticated:
        if _is_ajax(request):
            return JsonResponse({'error': 'login_required'}, status=401)
        return redirect('account_login')
    product = get_object_or_404(Product.objects.active(), pk=product_id)
    alert = PriceAlert.objects.filter(user=request.user, product=product).first()
    if alert and alert.notified_at is None:
        alert.delete()
        active = False
    else:
        PriceAlert.objects.update_or_create(
            user=request.user, product=product,
            defaults={'price_when_set': product.final_price, 'notified_at': None},
        )
        active = True
    msg = "We'll let you know when the price drops." if active else 'Price alert removed.'
    if _is_ajax(request):
        return JsonResponse({'active': active, 'message': msg})
    messages.success(request, msg)
    return redirect(product)


@login_required
@require_POST
def ask_question(request, slug):
    product = get_object_or_404(Product.objects.active(), slug=slug)
    if hit_limit(request, f'question:{request.user.id}', limit=5, window_seconds=3600):
        messages.error(request, 'You have asked a lot of questions recently. Please try again later.')
        return redirect(f'{product.get_absolute_url()}#questions')
    form = QuestionForm(request.POST)
    if form.is_valid():
        Question.objects.create(product=product, user=request.user, question=form.cleaned_data['question'])
        messages.success(request, 'Thanks! Your question was sent. We usually answer within a day.')
    else:
        messages.error(request, ' '.join(e for errors in form.errors.values() for e in errors))
    return redirect(f'{product.get_absolute_url()}#questions')


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
    photos = request.FILES.getlist('photos')
    image_field = forms.ImageField()
    try:
        if len(photos) > MAX_REVIEW_PHOTOS:
            raise forms.ValidationError(f'You can add up to {MAX_REVIEW_PHOTOS} photos.')
        for photo in photos:
            if photo.size > MAX_PHOTO_BYTES:
                raise forms.ValidationError('Each photo must be smaller than 5 MB.')
            image_field.clean(photo)
    except forms.ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
        return redirect(f'{product.get_absolute_url()}#reviews')
    if form.is_valid():
        review = form.save(commit=False)
        review.product = product
        review.user = request.user
        review.save()
        if photos:
            review.images.all().delete()
            for photo in photos:
                photo.seek(0)
                ReviewImage.objects.create(review=review, image=photo)
        messages.success(request, 'Thanks! Your review has been saved.')
    else:
        messages.error(request, 'Please choose a rating between 1 and 5.')
    return redirect(f'{product.get_absolute_url()}#reviews')
