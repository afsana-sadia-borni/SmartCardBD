from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from accounts.urls import newsletter_urlpatterns

admin.site.site_header = 'SmartCart BD Admin'
admin.site.site_title = 'SmartCart BD Admin'
admin.site.index_title = 'Store management'

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('profile/', include('accounts.urls')),
    path('newsletter/', include(newsletter_urlpatterns)),
    path('', include('core.urls')),
    path('cart/', include('cart.urls')),
    path('', include('orders.urls')),
    path('', include('products.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
