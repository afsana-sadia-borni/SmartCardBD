from django.utils.functional import SimpleLazyObject


def wishlist(request):
    def ids():
        if not request.user.is_authenticated:
            return set()
        return set(request.user.wishlist.values_list('product_id', flat=True))

    return {'wishlist_ids': SimpleLazyObject(ids)}


def notifications(request):
    """Unread count and the latest notifications for the bell in the top bar (queried only if used)."""
    user = getattr(request, 'user', None)

    def unread():
        return user.notifications.filter(is_read=False).count() if user and user.is_authenticated else 0

    def latest():
        return list(user.notifications.all()[:6]) if user and user.is_authenticated else []

    return {'unread_notifications': SimpleLazyObject(unread), 'latest_notifications': SimpleLazyObject(latest)}
