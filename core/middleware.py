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
