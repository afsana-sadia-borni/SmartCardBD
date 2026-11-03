from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('shop/', views.product_list, name='product_list'),
    path('search/suggest/', views.search_suggest, name='search_suggest'),
    path('compare/', views.compare, name='compare'),
    path('compare/clear/', views.compare_clear, name='compare_clear'),
    path('compare/toggle/<int:product_id>/', views.compare_toggle, name='compare_toggle'),
    path('price-alert/<int:product_id>/', views.price_alert_toggle, name='price_alert_toggle'),
    path('category/<slug:category_slug>/', views.product_list, name='category_detail'),
    path('product/<int:pk>/', views.product_detail_by_id, name='product_detail_by_id'),
    path('product/<slug:slug>/', views.product_detail, name='product_detail'),
    path('product/<slug:slug>/quick-view/', views.quick_view, name='quick_view'),
    path('product/<slug:slug>/review/', views.add_review, name='add_review'),
    path('product/<slug:slug>/question/', views.ask_question, name='ask_question'),
]
