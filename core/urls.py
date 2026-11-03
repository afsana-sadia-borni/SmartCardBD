from django.urls import path

from . import views

urlpatterns = [
    path('manifest.webmanifest', views.manifest, name='pwa_manifest'),
    path('sw.js', views.service_worker, name='service_worker'),
    path('offline/', views.offline, name='offline'),
    path('image-credits/', views.image_credits, name='image_credits'),
    path('robots.txt', views.robots_txt, name='robots_txt'),
]
