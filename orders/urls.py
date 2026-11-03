from django.urls import path

from django.views.generic import RedirectView

from . import reports, views

urlpatterns = [
    path('checkout/', views.checkout, name='checkout'),
    path('track/', views.track_order, name='track_order'),
    path('orders/', views.order_list, name='order_list'),
    path('orders/<str:order_number>/', views.order_detail, name='order_detail'),
    path('orders/<str:order_number>/success/', views.order_success, name='order_success'),
    path('orders/<str:order_number>/cancel/', views.order_cancel, name='order_cancel'),
    path('orders/<str:order_number>/invoice.pdf', views.order_invoice, name='order_invoice'),
    path('orders/<str:order_number>/pay/', views.order_pay, name='order_pay'),
    path('orders/<str:order_number>/return/', views.return_request, name='return_request'),
    path('orders/<str:order_number>/payment/<str:result>/', views.payment_result, name='payment_result'),

    path('payment/success/', views.payment_success, name='payment_success'),
    path('payment/fail/', views.payment_fail, name='payment_fail'),
    path('payment/cancel/', views.payment_cancel, name='payment_cancel'),
    path('payment/ipn/', views.payment_ipn, name='payment_ipn'),

    # The dashboard moved into the store panel.
    path('dashboard/', RedirectView.as_view(pattern_name='store:dashboard'), name='old_dashboard'),
    path('dashboard/sales.csv', reports.sales_report_csv, name='sales_report_csv'),
]
