from django.contrib import admin, messages

from .models import Coupon, Order, OrderItem
from .services import CheckoutError, cancel_order


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ['product', 'product_title', 'price', 'quantity', 'subtotal']

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
class OrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'full_name', 'phone', 'district', 'total', 'payment_method',
                    'payment_status', 'status', 'created_at']
    list_filter = ['status', 'payment_status', 'payment_method', 'created_at']
    search_fields = ['order_number', 'full_name', 'phone', 'email']
    readonly_fields = ['order_number', 'user', 'subtotal', 'discount', 'shipping_cost', 'total',
                       'coupon', 'transaction_id', 'created_at', 'updated_at']
    list_select_related = ['user']
    inlines = [OrderItemInline]
    date_hierarchy = 'created_at'
    actions = [_set_status(Order.Status.CONFIRMED), _set_status(Order.Status.SHIPPED),
               _set_status(Order.Status.DELIVERED), 'cancel_orders']
    fieldsets = [
        ('Order', {'fields': ['order_number', 'user', 'status', 'created_at', 'updated_at']}),
        ('Customer & shipping', {'fields': ['full_name', 'email', 'phone', 'district', 'area',
                                            'address_line', 'note']}),
        ('Payment', {'fields': ['payment_method', 'payment_status', 'transaction_id', 'coupon',
                                'subtotal', 'discount', 'shipping_cost', 'total']}),
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


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ['code', 'discount_type', 'value', 'min_order_amount', 'valid_from', 'valid_to',
                    'used_count', 'usage_limit', 'is_active']
    list_filter = ['is_active', 'discount_type']
    list_editable = ['is_active']
    search_fields = ['code']
    readonly_fields = ['used_count']
