from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from accounts.urls import newsletter_urlpatterns

admin.site.site_header = 'SmartCart BD Admin'
admin.site.site_title = 'SmartCart BD Admin'
admin.site.index_title = 'Store management'

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('profile/', include('accounts.urls')),
    path('newsletter/', include(newsletter_urlpatterns)),
    path('api/', include('api.urls')),
    path('store/', include('store.urls')),
    path('', include('core.urls')),
    path('cart/', include('cart.urls')),
    path('', include('orders.urls')),
    path('', include('products.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    if settings.ADMIN_URL != 'admin/':
        # Convenience while developing: /admin/ still works. On the live site it stays a 404.
        urlpatterns.insert(0, path('admin/', RedirectView.as_view(url='/' + settings.ADMIN_URL)))
