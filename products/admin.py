from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin

from .models import (Banner, Bundle, Category, FlashSale, PriceAlert, Product, ProductImage, ProductVariant,
                     Question, Review, ReviewImage)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name']


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ['image', 'preview', 'alt', 'color', 'sort_order']
    readonly_fields = ['preview']

    @admin.display(description='Preview')
    def preview(self, obj):
        return format_html('<img src="{}" style="height:60px;border-radius:6px">', obj.image.url) if obj.image else ''


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = ['color', 'size', 'storage', 'sku', 'price', 'discount_price', 'stock', 'is_active']


@admin.register(Product)
class ProductAdmin(SimpleHistoryAdmin):
    list_display = ['thumb', 'title', 'category', 'brand', 'price', 'discount_price', 'stock', 'is_active',
                    'is_featured', 'created_at']
    list_display_links = ['thumb', 'title']
    list_filter = ['is_active', 'is_featured', 'category', 'created_at']
    list_editable = ['price', 'discount_price', 'stock', 'is_active', 'is_featured']
    search_fields = ['title', 'brand', 'description']
    prepopulated_fields = {'slug': ('title',)}
    list_select_related = ['category']
    inlines = [ProductImageInline, ProductVariantInline]

    @admin.display(description='')
    def thumb(self, obj):
        return format_html('<img src="{}" style="height:40px;width:40px;object-fit:cover;border-radius:6px">',
                           obj.image.url) if obj.image else ''


class ReviewImageInline(admin.TabularInline):
    model = ReviewImage
    extra = 0


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['product', 'user', 'rating', 'created_at']
    list_filter = ['rating', 'created_at']
    search_fields = ['product__title', 'user__email', 'comment']
    list_select_related = ['product', 'user']
    inlines = [ReviewImageInline]


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ['preview', 'title', 'link_url', 'sort_order', 'is_active', 'starts_at', 'ends_at']
    list_display_links = ['preview', 'title']
    list_editable = ['sort_order', 'is_active']

    @admin.display(description='')
    def preview(self, obj):
        return format_html('<img src="{}" style="height:40px;border-radius:6px">', obj.image.url) if obj.image else ''


@admin.register(FlashSale)
class FlashSaleAdmin(SimpleHistoryAdmin):
    list_display = ['title', 'discount_percent', 'starts_at', 'ends_at', 'is_running', 'is_active']
    list_filter = ['is_active']
    filter_horizontal = ['products']

    @admin.display(boolean=True, description='Running now')
    def is_running(self, obj):
        return obj.is_active and obj.starts_at <= timezone.now() < obj.ends_at


@admin.register(Bundle)
class BundleAdmin(admin.ModelAdmin):
    list_display = ['title', 'bundle_price', 'regular', 'is_active']
    list_editable = ['is_active']
    filter_horizontal = ['products']

    @admin.display(description='Regular total')
    def regular(self, obj):
        return obj.regular_total()


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['question_short', 'product', 'user', 'answered', 'is_published', 'created_at']
    list_filter = ['is_published', ('answered_at', admin.EmptyFieldListFilter), 'created_at']
    search_fields = ['question', 'answer', 'product__title', 'user__email']
    list_select_related = ['product', 'user']
    readonly_fields = ['product', 'user', 'question', 'answered_by', 'answered_at', 'created_at']
    fields = ['product', 'user', 'question', 'answer', 'is_published', 'answered_by', 'answered_at', 'created_at']

    @admin.display(description='Question')
    def question_short(self, obj):
        return obj.question[:70]

    @admin.display(boolean=True)
    def answered(self, obj):
        return bool(obj.answered_at)

    def save_model(self, request, obj, form, change):
        newly_answered = obj.answer and 'answer' in form.changed_data
        if newly_answered:
            obj.answered_by = request.user
            obj.answered_at = timezone.now()
        super().save_model(request, obj, form, change)
        if newly_answered:
            from accounts.services import notify

            notify(obj.user, f'Your question about "{obj.product.title}" has been answered.',
                   url=f'{obj.product.get_absolute_url()}#questions', icon='chat-dots')


@admin.register(PriceAlert)
class PriceAlertAdmin(admin.ModelAdmin):
    list_display = ['product', 'user', 'price_when_set', 'created_at', 'notified_at']
    list_filter = [('notified_at', admin.EmptyFieldListFilter)]
    list_select_related = ['product', 'user']
    readonly_fields = ['product', 'user', 'price_when_set', 'created_at', 'notified_at']
