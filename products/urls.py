from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('shop/', views.product_list, name='product_list'),
    path('category/<slug:category_slug>/', views.product_list, name='category_detail'),
    path('product/<int:pk>/', views.product_detail_by_id, name='product_detail_by_id'),
    path('product/<slug:slug>/', views.product_detail, name='product_detail'),
    path('product/<slug:slug>/review/', views.add_review, name='add_review'),
]
