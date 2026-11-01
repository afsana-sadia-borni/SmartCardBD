from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from products.models import Product

from .forms import AddressForm
from .models import Address, Wishlist


@login_required
def profile(request):
    return render(request, 'accounts/profile.html', {
        'recent_orders': request.user.orders.all()[:5],
        'addresses': request.user.addresses.all(),
        'wishlist_count': request.user.wishlist.count(),
    })


@login_required
def address_form(request, pk=None):
    address = get_object_or_404(Address, pk=pk, user=request.user) if pk else None
    form = AddressForm(request.POST or None, instance=address)
    if request.method == 'POST' and form.is_valid():
        address = form.save(commit=False)
        address.user = request.user
        address.save()
        messages.success(request, 'Address saved.')
        return redirect('profile')
    return render(request, 'accounts/address_form.html', {'form': form, 'address': address})


@login_required
@require_POST
def address_delete(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    was_default = address.is_default
    address.delete()
    if was_default:
        next_default = request.user.addresses.first()
        if next_default:
            next_default.is_default = True
            next_default.save()
    messages.success(request, 'Address deleted.')
    return redirect('profile')


@login_required
@require_POST
def address_make_default(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    address.is_default = True
    address.save()
    return redirect('profile')


@login_required
def wishlist(request):
    items = request.user.wishlist.select_related('product__category').filter(product__is_active=True)
    return render(request, 'accounts/wishlist.html', {'items': items})


@require_POST
def wishlist_toggle(request, product_id):
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    if not request.user.is_authenticated:
        if is_ajax:
            return JsonResponse({'error': 'login_required'}, status=401)
        return redirect('account_login')

    product = get_object_or_404(Product.objects.active(), pk=product_id)
    item, created = Wishlist.objects.get_or_create(user=request.user, product=product)
    if not created:
        item.delete()

    if is_ajax:
        return JsonResponse({'in_wishlist': created, 'count': request.user.wishlist.count()})
    messages.success(request, 'Added to wishlist.' if created else 'Removed from wishlist.')
    next_url = request.POST.get('next')
    if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}, request.is_secure()):
        return redirect(next_url)
    return redirect(product)
