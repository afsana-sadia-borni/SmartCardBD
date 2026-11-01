from django.urls import path

from . import dashboard, views

urlpatterns = [
    path('checkout/', views.checkout, name='checkout'),
    path('orders/', views.order_list, name='order_list'),
    path('orders/<str:order_number>/', views.order_detail, name='order_detail'),
    path('orders/<str:order_number>/success/', views.order_success, name='order_success'),
    path('orders/<str:order_number>/cancel/', views.order_cancel, name='order_cancel'),
    path('orders/<str:order_number>/pay/', views.order_pay, name='order_pay'),
    path('orders/<str:order_number>/payment/<str:result>/', views.payment_result, name='payment_result'),

    path('payment/success/', views.payment_success, name='payment_success'),
    path('payment/fail/', views.payment_fail, name='payment_fail'),
    path('payment/cancel/', views.payment_cancel, name='payment_cancel'),
    path('payment/ipn/', views.payment_ipn, name='payment_ipn'),

    path('dashboard/', dashboard.dashboard, name='dashboard'),
]
