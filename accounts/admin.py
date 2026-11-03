from django.contrib import admin

from .models import Address, CustomerProfile, Notification, PointTransaction, PushSubscription, Subscriber, Wishlist


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'user', 'phone', 'district', 'upazila', 'area', 'is_default']
    list_filter = ['district', 'is_default']
    search_fields = ['full_name', 'phone', 'user__email']


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ['user', 'product', 'created_at']
    search_fields = ['user__email', 'product__title']
    list_select_related = ['user', 'product']


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'points', 'referral_code', 'referred_by', 'referral_rewarded']
    search_fields = ['user__email', 'referral_code']
    list_select_related = ['user', 'referred_by']
    readonly_fields = ['referral_code']


@admin.register(PointTransaction)
class PointTransactionAdmin(admin.ModelAdmin):
    list_display = ['user', 'points', 'reason', 'order', 'created_at']
    search_fields = ['user__email', 'reason']
    list_select_related = ['user', 'order']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'message', 'is_read', 'created_at']
    list_filter = ['is_read', 'created_at']
    search_fields = ['user__email', 'message']
    list_select_related = ['user']


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['user', 'created_at']
    search_fields = ['user__email']
    list_select_related = ['user']
    readonly_fields = ['user', 'endpoint', 'p256dh', 'auth', 'created_at']


@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ['email', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['email']
    actions = ['export_csv']

    @admin.action(description='Download selected as CSV')
    def export_csv(self, request, queryset):
        import csv

        from django.http import HttpResponse

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="subscribers.csv"'
        writer = csv.writer(response)
        writer.writerow(['Email', 'Active', 'Subscribed'])
        for s in queryset:
            writer.writerow([s.email, s.is_active, s.created_at.date()])
        return response
