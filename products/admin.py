from django.contrib import admin

from .models import Category, Product, Review


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'brand', 'price', 'discount_price', 'stock', 'is_active',
                    'is_featured', 'created_at']
    list_filter = ['is_active', 'is_featured', 'category', 'created_at']
    list_editable = ['price', 'discount_price', 'stock', 'is_active', 'is_featured']
    search_fields = ['title', 'brand', 'description']
    prepopulated_fields = {'slug': ('title',)}
    list_select_related = ['category']


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['product', 'user', 'rating', 'created_at']
    list_filter = ['rating', 'created_at']
    search_fields = ['product__title', 'user__email', 'comment']
    list_select_related = ['product', 'user']
