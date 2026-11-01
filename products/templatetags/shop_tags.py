from decimal import Decimal, InvalidOperation

from django import template
from django.contrib.humanize.templatetags.humanize import intcomma

register = template.Library()


@register.filter
def taka(value):
    """12500.00 -> '৳12,500', 99.50 -> '৳99.50'."""
    try:
        amount = Decimal(value)
    except (TypeError, ValueError, InvalidOperation):
        return value
    text = f'{amount:.0f}' if amount == amount.to_integral_value() else f'{amount:.2f}'
    return f'৳{intcomma(text)}'


@register.inclusion_tag('partials/stars.html')
def stars(rating, count=None):
    rating = float(rating or 0)
    icons = []
    for i in range(1, 6):
        if rating >= i - 0.25:
            icons.append('star-fill')
        elif rating >= i - 0.75:
            icons.append('star-half')
        else:
            icons.append('star')
    return {'icons': icons, 'rating': rating, 'count': count}


@register.simple_tag(takes_context=True)
def query_transform(context, **kwargs):
    """Return the current querystring with some params replaced, e.g. {% query_transform page=2 %}."""
    params = context['request'].GET.copy()
    for key, value in kwargs.items():
        if value in (None, ''):
            params.pop(key, None)
        else:
            params[key] = value
    return params.urlencode()


@register.simple_tag(takes_context=True)
def nav_active(context, url, exact=False):
    """Return 'active' when the current page is `url` (or below it, unless exact)."""
    request = context.get('request')
    if request is None:
        return ''
    matches = request.path == url if exact else request.path.startswith(url)
    return 'active' if matches else ''
