from django.urls import path

from . import views

urlpatterns = [
    path('', views.cart_summary, name='cart_summary'),
    path('mini/', views.mini_cart, name='mini_cart'),
    path('add/', views.cart_add, name='cart_add'),
    path('update/', views.cart_update, name='cart_update'),
    path('remove/', views.cart_remove, name='cart_remove'),
    path('coupon/apply/', views.coupon_apply, name='coupon_apply'),
    path('coupon/remove/', views.coupon_remove, name='coupon_remove'),
]
