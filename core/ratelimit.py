from django.core.cache import cache


def client_ip(request):
    return request.META.get('REMOTE_ADDR', '')


def hit_limit(request, scope, limit, window_seconds):
    """Count one hit for this client; return True once it exceeds `limit` hits per window."""
    key = f'rl:{scope}:{client_ip(request)}'
    if cache.add(key, 1, window_seconds):
        return False
    try:
        return cache.incr(key) > limit
    except ValueError:  # expired between add and incr
        cache.set(key, 1, window_seconds)
        return False
