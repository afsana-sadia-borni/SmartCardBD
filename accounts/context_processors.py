from django.utils.functional import SimpleLazyObject


def wishlist(request):
    def ids():
        if not request.user.is_authenticated:
            return set()
        return set(request.user.wishlist.values_list('product_id', flat=True))

    return {'wishlist_ids': SimpleLazyObject(ids)}
