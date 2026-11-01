from django.urls import path

from . import views

urlpatterns = [
    path('', views.profile, name='profile'),
    path('addresses/new/', views.address_form, name='address_add'),
    path('addresses/<int:pk>/edit/', views.address_form, name='address_edit'),
    path('addresses/<int:pk>/delete/', views.address_delete, name='address_delete'),
    path('addresses/<int:pk>/default/', views.address_make_default, name='address_make_default'),
    path('wishlist/', views.wishlist, name='wishlist'),
    path('wishlist/toggle/<int:product_id>/', views.wishlist_toggle, name='wishlist_toggle'),
]
