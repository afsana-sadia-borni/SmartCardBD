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
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/<int:pk>/', views.notification_open, name='notification_open'),
    path('notifications/read/', views.notifications_mark_read, name='notifications_mark_read'),
    path('push/subscribe/', views.push_subscribe, name='push_subscribe'),
    path('push/unsubscribe/', views.push_unsubscribe, name='push_unsubscribe'),
]

newsletter_urlpatterns = [
    path('subscribe/', views.newsletter_subscribe, name='newsletter_subscribe'),
    path('unsubscribe/<str:token>/', views.newsletter_unsubscribe, name='newsletter_unsubscribe'),
]
