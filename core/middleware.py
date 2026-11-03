from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse

from .numerals import use_bn_digits

DIGITS_COOKIE = 'digits'
REFERRAL_SESSION_KEY = 'referral_code'


class ShopPreferencesMiddleware:
    """Per-request shop preferences: Bangla digits (cookie) and referral links (?ref=CODE)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ref = request.GET.get('ref', '').strip().upper()
        if ref and len(ref) <= 20:
            request.session[REFERRAL_SESSION_KEY] = ref

        request.bn_digits = request.COOKIES.get(DIGITS_COOKIE) == 'bn'
        token = use_bn_digits.set(request.bn_digits)
        try:
            return self.get_response(request)
        finally:
            use_bn_digits.reset(token)


class DemoAccountGuardMiddleware:
    """Keep the shared demo account usable: visitors can shop with it, but not change its
    password or email, or delete it."""

    PROTECTED = ('account_change_password', 'account_set_password', 'account_email')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if (request.method == 'POST' and user is not None and user.is_authenticated
                and user.email.lower() == settings.DEMO_EMAIL.lower()
                and request.path in {reverse(name) for name in self.PROTECTED}):
            messages.info(request, "The demo account's login details can't be changed. Sign up to get your own account.")
            return redirect('profile')
        return self.get_response(request)
