from django.contrib import admin

from .models import Address, Wishlist


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'user', 'phone', 'district', 'area', 'is_default']
    list_filter = ['district', 'is_default']
    search_fields = ['full_name', 'phone', 'user__email']


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ['user', 'product', 'created_at']
    search_fields = ['user__email', 'product__title']
    list_select_related = ['user', 'product']
