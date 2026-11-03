from django.conf import settings


def shop(request):
    return {
        'whatsapp_number': settings.WHATSAPP_NUMBER,
        'messenger_url': settings.MESSENGER_URL,
        'bn_digits': getattr(request, 'bn_digits', False),
        'compare_ids': request.session.get('compare', []) if hasattr(request, 'session') else [],
        'demo_login': {'email': settings.DEMO_EMAIL, 'password': settings.DEMO_PASSWORD} if settings.SHOW_DEMO_LOGIN else None,
    }
