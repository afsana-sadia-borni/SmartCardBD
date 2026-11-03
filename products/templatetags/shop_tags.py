import json
from decimal import Decimal, InvalidOperation

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

from core.numerals import localize_digits, use_bn_digits
from products import images

register = template.Library()


def lakh_group(digits):
    """'1250000' -> '12,50,000' (Bangladeshi/Indian grouping)."""
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ','.join(groups) + ',' + tail


@register.filter
def taka(value):
    """1250000 -> '৳12,50,000', 99.50 -> '৳99.50'; Bangla digits when the visitor chose them."""
    try:
        amount = Decimal(value)
    except (TypeError, ValueError, InvalidOperation):
        return value
    negative = amount < 0
    amount = abs(amount)
    whole = amount.to_integral_value()
    text = lakh_group(f'{whole:.0f}') if amount == whole else f'{lakh_group(f"{int(amount)}")}.{f"{amount:.2f}"[-2:]}'
    return localize_digits(f'{"-" if negative else ""}৳{text}')


@register.filter
def num(value):
    """Format a whole number with lakh grouping (and Bangla digits when chosen)."""
    try:
        return localize_digits(lakh_group(str(int(value))))
    except (TypeError, ValueError):
        return value


@register.filter
def sold_label(count):
    """Real units sold: '7 sold', '120+ sold' / '১২০+ বিক্রি হয়েছে'."""
    try:
        count = int(count)
    except (TypeError, ValueError):
        return ''
    if count <= 0:
        return ''
    shown = f'{count}' if count < 10 else f'{count // 10 * 10}+'
    if use_bn_digits.get():
        return f'{localize_digits(shown)} বিক্রি হয়েছে'
    return f'{shown} sold'


@register.filter
def json_attr(value):
    """JSON for an HTML data- attribute."""
    return mark_safe(escape(json.dumps(value)))


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

@register.filter
def webp(url, width=400):
    """{{ product.image.url|webp:400 }}: the small WebP copy of an uploaded image (or the original)."""
    return images.webp_url(url, int(width))
