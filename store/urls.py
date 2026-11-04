from django.urls import path

from . import catalog, reports, support, views

app_name = 'store'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('reports/', reports.reports, name='reports'),
    path('orders/', views.order_list, name='orders'),
    path('orders/bulk/', views.orders_bulk, name='orders_bulk'),
    path('orders/slips/', views.packing_slips, name='packing_slips'),
    path('orders/<str:order_number>/', views.order_detail, name='order_detail'),
    path('orders/<str:order_number>/action/', views.order_action, name='order_action'),
    path('returns/', support.return_list, name='returns'),
    path('returns/<int:pk>/decide/', support.return_decide, name='return_decide'),
    path('questions/', support.question_list, name='questions'),
    path('questions/<int:pk>/answer/', support.question_answer, name='question_answer'),
    path('customers/', views.customer_list, name='customers'),
    path('products/', catalog.product_list, name='products'),
    path('products/new/', catalog.product_form, name='product_add'),
    path('products/export.csv', catalog.products_export, name='products_export'),
    path('products/import/', catalog.products_import, name='products_import'),
    path('products/<int:pk>/', catalog.product_form, name='product_edit'),
    path('products/<int:pk>/quick/', catalog.product_quick_update, name='product_quick_update'),
    path('flash-sales/', catalog.flash_sale_list, name='flash_sales'),
    path('flash-sales/new/', catalog.flash_sale_form, name='flash_sale_add'),
    path('flash-sales/<int:pk>/', catalog.flash_sale_form, name='flash_sale_edit'),
    path('coupons/', catalog.coupon_list, name='coupons'),
    path('coupons/new/', catalog.coupon_form, name='coupon_add'),
    path('coupons/<int:pk>/', catalog.coupon_form, name='coupon_edit'),
    path('banners/', catalog.banner_list, name='banners'),
    path('banners/new/', catalog.banner_form, name='banner_add'),
    path('banners/<int:pk>/', catalog.banner_form, name='banner_edit'),
    path('banners/<int:pk>/delete/', catalog.banner_delete, name='banner_delete'),
    path('delivery/', catalog.delivery_list, name='delivery'),
    path('delivery/new/', catalog.delivery_form, name='delivery_add'),
    path('delivery/<int:pk>/', catalog.delivery_form, name='delivery_edit'),
    path('team/', views.team, name='team'),
    path('integrations/', views.integrations, name='integrations'),
    path('team/<int:user_id>/remove/', views.team_remove, name='team_remove'),
]
