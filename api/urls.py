from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

router = DefaultRouter()
router.register('orders', views.OrderViewSet, basename='api-order')

urlpatterns = [
    path('auth/token/', views.LoginView.as_view(), name='api_token'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='api_token_refresh'),
    path('categories/', views.CategoryList.as_view(), name='api_categories'),
    path('products/', views.ProductList.as_view(), name='api_products'),
    path('products/<slug:slug>/', views.ProductDetail.as_view(), name='api_product_detail'),
    path('me/', views.ProfileView.as_view(), name='api_me'),
    path('schema/', SpectacularAPIView.as_view(), name='api_schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='api_schema'), name='api_docs'),
    path('', include(router.urls)),
]
