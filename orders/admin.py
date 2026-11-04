from django.contrib import admin, messages
from django.utils import timezone
from simple_history.admin import SimpleHistoryAdmin

from .forms import DeliveryZoneForm
from .models import BlockedPhone, Coupon, DeliveryZone, Order, OrderItem, ReturnRequest
from .reports import orders_csv_response
from .services import CheckoutError, cancel_order


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ['product', 'product_title', 'variant_label', 'price', 'quantity', 'subtotal']

    def has_add_permission(self, request, obj=None):
        return False


def _set_status(status):
    def action(modeladmin, request, queryset):
        # Save one by one so the status-change email signal fires for each order.
        updated = 0
        for order in queryset.exclude(status=Order.Status.CANCELLED):
            order.status = status
            order.save(update_fields=['status', 'updated_at'])
            updated += 1
        modeladmin.message_user(request, f'{updated} order(s) marked as {Order.Status(status).label}.')
    action.short_description = f'Mark selected as {Order.Status(status).label}'
    action.__name__ = f'mark_{status}'
    return action


@admin.register(Order)
class OrderAdmin(SimpleHistoryAdmin):
    list_display = ['order_number', 'full_name', 'phone', 'district', 'total', 'payment_method',
                    'payment_status', 'status', 'created_at']
    list_filter = ['status', 'payment_status', 'payment_method', 'payment_channel', 'created_at']
    search_fields = ['order_number', 'full_name', 'phone', 'email']
    readonly_fields = ['order_number', 'user', 'subtotal', 'discount', 'bundle_discount', 'points_used',
                       'points_discount', 'gift_wrap_cost', 'shipping_cost', 'total', 'coupon', 'transaction_id',
                       'points_earned', 'created_at', 'updated_at']
    list_select_related = ['user']
    inlines = [OrderItemInline]
    date_hierarchy = 'created_at'
    actions = [_set_status(Order.Status.CONFIRMED), _set_status(Order.Status.SHIPPED),
               _set_status(Order.Status.DELIVERED), 'cancel_orders', 'export_csv']
    fieldsets = [
        ('Order', {'fields': ['order_number', 'user', 'status', 'created_at', 'updated_at']}),
        ('Customer & shipping', {'fields': ['full_name', 'email', 'phone', 'district', 'upazila', 'area',
                                            'address_line', 'note', 'gift_wrap', 'delivery_estimate']}),
        ('Courier & checks', {'fields': ['courier_name', 'courier_consignment_id', 'courier_tracking_code',
                                         'courier_tracking_link', 'courier_status', 'risk_flags']}),
        ('Payment', {'fields': ['payment_method', 'payment_channel', 'payment_status', 'transaction_id', 'coupon',
                                'subtotal', 'discount', 'bundle_discount', 'points_used', 'points_discount',
                                'gift_wrap_cost', 'shipping_cost', 'total', 'points_earned']}),
    ]

    def save_model(self, request, obj, form, change):
        cancelling = change and 'status' in form.changed_data and obj.status == Order.Status.CANCELLED
        if not cancelling:
            return super().save_model(request, obj, form, change)
        # Route cancellations through the service so stock and coupon usage are restored.
        obj.status = form.initial['status']
        super().save_model(request, obj, form, change)
        try:
            cancel_order(obj, by_staff=True)
            obj.status = Order.Status.CANCELLED
        except CheckoutError as exc:
            self.message_user(request, str(exc), messages.ERROR)

    @admin.action(description='Cancel selected orders (restock items)')
    def cancel_orders(self, request, queryset):
        done = 0
        for order in queryset:
            try:
                cancel_order(order, by_staff=True)
                done += 1
            except CheckoutError:
                pass
        self.message_user(request, f'{done} order(s) cancelled.', messages.SUCCESS if done else messages.WARNING)


    @admin.action(description='Download selected as CSV (sales report)')
    def export_csv(self, request, queryset):
        return orders_csv_response(queryset.order_by('created_at'), f'orders-{timezone.localdate():%Y%m%d}.csv')


@admin.register(Coupon)
class CouponAdmin(SimpleHistoryAdmin):
    list_display = ['code', 'discount_type', 'value', 'min_order_amount', 'valid_from', 'valid_to',
                    'used_count', 'usage_limit', 'user', 'is_active']
    raw_id_fields = ['user']
    list_filter = ['is_active', 'discount_type']
    list_editable = ['is_active']
    search_fields = ['code']
    readonly_fields = ['used_count']


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    form = DeliveryZoneForm
    list_display = ['name', 'charge', 'min_days', 'max_days', 'district_count', 'is_default', 'sort_order']
    list_editable = ['charge', 'min_days', 'max_days', 'sort_order']

    @admin.display(description='Districts')
    def district_count(self, obj):
        return 'All others' if obj.is_default and not obj.districts else len(obj.districts)


@admin.register(ReturnRequest)
class ReturnRequestAdmin(SimpleHistoryAdmin):
    list_display = ['order', 'reason', 'status', 'created_at']
    list_filter = ['status', 'reason', 'created_at']
    search_fields = ['order__order_number', 'order__phone', 'order__email']
    readonly_fields = ['order', 'reason', 'details', 'photo', 'created_at', 'updated_at']
    list_select_related = ['order']
    actions = ['approve', 'reject', 'mark_refunded']

    def _set(self, request, queryset, status):
        count = 0
        for rr in queryset:
            rr.status = status
            rr.save(update_fields=['status', 'updated_at'])  # one by one so customers get notified
            count += 1
        self.message_user(request, f'{count} return request(s) updated.')

    @admin.action(description='Approve selected returns')
    def approve(self, request, queryset):
        self._set(request, queryset, ReturnRequest.Status.APPROVED)

    @admin.action(description='Reject selected returns')
    def reject(self, request, queryset):
        self._set(request, queryset, ReturnRequest.Status.REJECTED)

    @admin.action(description='Mark selected as refunded')
    def mark_refunded(self, request, queryset):
        self._set(request, queryset, ReturnRequest.Status.REFUNDED)


@admin.register(BlockedPhone)
class BlockedPhoneAdmin(admin.ModelAdmin):
    list_display = ['phone', 'reason', 'created_by', 'created_at']
    search_fields = ['phone', 'reason']
    readonly_fields = ['created_by', 'created_at']
