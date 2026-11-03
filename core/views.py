import json

from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.views.decorators.cache import cache_control

CREDITS_FILE = settings.BASE_DIR / 'products' / 'demo_media' / 'credits.json'

# slug: (title, last updated)
POLICY_PAGES = {
    'about': ('About us', ''),
    'shipping': ('Delivery policy', '3 November 2026'),
    'returns': ('Return & refund policy', '3 November 2026'),
    'privacy': ('Privacy policy', '3 November 2026'),
    'terms': ('Terms & conditions', '3 November 2026'),
}


@cache_control(max_age=86400, public=True)
def manifest(request):
    icons = [
        {'src': static('img/icons/icon-192.png'), 'sizes': '192x192', 'type': 'image/png'},
        {'src': static('img/icons/icon-512.png'), 'sizes': '512x512', 'type': 'image/png'},
        {'src': static('img/icons/icon-maskable-512.png'), 'sizes': '512x512', 'type': 'image/png',
         'purpose': 'maskable'},
    ]
    data = {
        'name': settings.SITE_NAME,
        'short_name': 'SmartCart',
        'description': 'Smart online shopping for Bangladesh. Cash on Delivery across all 64 districts.',
        'start_url': '/?source=pwa',
        'scope': '/',
        'display': 'standalone',
        'background_color': '#212529',
        'theme_color': '#212529',
        'icons': icons,
    }
    return JsonResponse(data, content_type='application/manifest+json')


@cache_control(no_cache=True)
def service_worker(request):
    response = render(request, 'core/sw.js', {
        'precache': [static('css/style.css'), static('js/script.js'), static('img/no-image.svg'),
                     static('img/icons/icon-192.png')],
        'icon_url': static('img/icons/icon-192.png'),
    }, content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    return response


@cache_control(max_age=86400, public=True)
def favicon(request):
    """Browsers ask for /favicon.ico on their own (e.g. on pages without our <link rel="icon">)."""
    return redirect(static('img/favicon.svg'), permanent=True)


def offline(request):
    return render(request, 'core/offline.html')


def image_credits(request):
    try:
        credits = json.loads(CREDITS_FILE.read_text())
    except (OSError, ValueError):
        credits = {}
    return render(request, 'core/credits.html', {'credits': sorted(credits.items())})


def robots_txt(request):
    lines = ['User-agent: *', f'Disallow: /{settings.ADMIN_URL}', 'Disallow: /cart/', 'Disallow: /checkout/',
             'Disallow: /orders/', 'Disallow: /profile/', 'Disallow: /dashboard/', 'Disallow: /store/']
    return HttpResponse('\n'.join(lines) + '\n', content_type='text/plain')


def policy_page(request, slug):
    if slug not in POLICY_PAGES:
        raise Http404
    from orders import payments
    from orders.models import DeliveryZone

    title, updated = POLICY_PAGES[slug]
    return render(request, f'core/pages/{slug}.html', {
        'page_title': title,
        'updated': updated,
        'current_slug': slug,
        'policy_links': [(key, value[0]) for key, value in POLICY_PAGES.items()],
        'zones': DeliveryZone.objects.all() if slug == 'shipping' else [],
        'online_payment': payments.is_configured(),
        'return_days': settings.RETURN_WINDOW_DAYS,
        'free_shipping_min': settings.FREE_SHIPPING_MIN,
        'inside_dhaka': settings.SHIPPING_INSIDE_DHAKA,
        'outside_dhaka': settings.SHIPPING_OUTSIDE_DHAKA,
        'gift_wrap_price': settings.GIFT_WRAP_PRICE,
        'unpaid_minutes': settings.UNPAID_ORDER_TIMEOUT_MINUTES,
        'lockout_attempts': settings.AXES_FAILURE_LIMIT,
        'points_per_taka': settings.POINTS_PER_TAKA,
        'points_block': settings.POINTS_REDEEM_BLOCK,
        'points_value': settings.POINTS_REDEEM_VALUE,
        'referral_reward': settings.REFERRAL_REWARD,
        'support_email': settings.SUPPORT_EMAIL,
        'support_phone': settings.SUPPORT_PHONE,
        'business_address': settings.BUSINESS_ADDRESS,
        'trade_license': settings.TRADE_LICENSE,
    })
