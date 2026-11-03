from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core.ratelimit import hit_limit
from products.models import Product

from .forms import AddressForm, NewsletterForm
from .models import Address, Notification, PushSubscription, Subscriber, Wishlist, get_profile
from .push import push_enabled


@login_required
def profile(request):
    profile = get_profile(request.user)
    referral_link = request.build_absolute_uri(f'/accounts/signup/?ref={profile.referral_code}')
    return render(request, 'accounts/profile.html', {
        'recent_orders': request.user.orders.all()[:5],
        'addresses': request.user.addresses.all(),
        'wishlist_count': request.user.wishlist.count(),
        'loyalty': profile,
        'referral_link': referral_link,
        'referral_count': request.user.referrals.count(),
        'point_history': request.user.point_transactions.all()[:10],
        'coupons': request.user.coupons.filter(is_active=True, used_count=0),
    })


@login_required
def notifications(request):
    items = list(request.user.notifications.all()[:50])
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return render(request, 'accounts/notifications.html', {
        'items': items, 'vapid_public_key': settings.VAPID_PUBLIC_KEY if push_enabled() else '',
    })


@login_required
def notification_open(request, pk):
    note = get_object_or_404(Notification, pk=pk, user=request.user)
    if not note.is_read:
        note.is_read = True
        note.save(update_fields=['is_read'])
    target = note.url if note.url and url_has_allowed_host_and_scheme(note.url, {request.get_host()}) else None
    return redirect(target or 'notifications')


@login_required
@require_POST
def notifications_mark_read(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    return redirect('notifications')


@login_required
@require_POST
def push_subscribe(request):
    """Save this browser's push subscription (sent by the 'Turn on' button on the notifications page)."""
    endpoint = request.POST.get('endpoint', '')
    p256dh, auth = request.POST.get('p256dh', ''), request.POST.get('auth', '')
    if not (endpoint.startswith('https://') and len(endpoint) <= 500 and p256dh and auth):
        return JsonResponse({'ok': False}, status=400)
    PushSubscription.objects.update_or_create(
        endpoint=endpoint, defaults={'user': request.user, 'p256dh': p256dh[:200], 'auth': auth[:100]},
    )
    return JsonResponse({'ok': True})


@login_required
@require_POST
def push_unsubscribe(request):
    PushSubscription.objects.filter(user=request.user, endpoint=request.POST.get('endpoint', '')).delete()
    return JsonResponse({'ok': True})


@require_POST
def newsletter_subscribe(request):
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    if hit_limit(request, 'newsletter', limit=5, window_seconds=600):
        ok, msg = False, 'Too many attempts. Please try again later.'
    else:
        email = request.POST.get('email', '').strip().lower()
        existing = Subscriber.objects.filter(email__iexact=email).first()
        form = NewsletterForm(request.POST, instance=existing)
        if existing and form.is_valid():
            existing.is_active = True
            existing.save(update_fields=['is_active'])
            ok, msg = True, "You're subscribed. Thanks!"
        elif form.is_valid():
            subscriber = form.save(commit=False)
            subscriber.email = email
            subscriber.save()
            ok, msg = True, "You're subscribed. Watch your inbox for deals!"
        else:
            ok, msg = False, ' '.join(e for errors in form.errors.values() for e in errors)
    if is_ajax:
        return JsonResponse({'ok': ok, 'message': msg}, status=200 if ok else 400)
    (messages.success if ok else messages.error)(request, msg)
    next_url = request.POST.get('next')
    if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}, request.is_secure()):
        return redirect(next_url)
    return redirect('home')


def newsletter_unsubscribe(request, token):
    subscriber = get_object_or_404(Subscriber, token=token)
    if request.method == 'POST':
        subscriber.is_active = False
        subscriber.save(update_fields=['is_active'])
        messages.success(request, 'You have been unsubscribed.')
        return redirect('home')
    return render(request, 'accounts/unsubscribe.html', {'subscriber': subscriber})


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
