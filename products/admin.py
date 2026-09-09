from django.contrib import admin
from .models import Category, Product

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'price', 'stock', 'created_at']
    list_filter = ['category', 'created_at']
    list_editable = ['price', 'stock']
    prepopulated_fields = {'slug': ('title',)}

