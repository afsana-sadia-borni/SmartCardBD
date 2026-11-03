import json

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.views.decorators.cache import cache_control

CREDITS_FILE = settings.BASE_DIR / 'products' / 'demo_media' / 'credits.json'


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
    }, content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    return response


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
             'Disallow: /orders/', 'Disallow: /profile/', 'Disallow: /dashboard/']
    return HttpResponse('\n'.join(lines) + '\n', content_type='text/plain')
