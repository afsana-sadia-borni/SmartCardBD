from django.conf import settings
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, mixins, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from accounts.models import get_profile
from cart.cart import make_key
from orders.forms import CheckoutForm
from orders.models import Coupon, Order
from orders.services import CheckoutError, create_order, release_unpaid_orders
from products.filters import SORT_OPTIONS, filter_products
from products.models import Category, Review
from products.views import shop_products

from .serializers import (CategorySerializer, EmailTokenObtainPairSerializer, OrderCreateSerializer, OrderSerializer,
                          ProductDetailSerializer, ProductListSerializer, ProfileSerializer)


class LoginView(TokenObtainPairView):
    """Get a JWT access token (and a refresh token) with your email and password.

    Send it as `Authorization: Bearer <access>`. Repeated failed logins lock the account like on the website.
    """

    serializer_class = EmailTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'


class CategoryList(generics.ListAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    pagination_class = None


@extend_schema(parameters=[
    OpenApiParameter('q', OpenApiTypes.STR, description='Search title, brand, category and description'),
    OpenApiParameter('category', OpenApiTypes.STR, description='Category slug'),
    OpenApiParameter('brand', OpenApiTypes.STR),
    OpenApiParameter('min_price', OpenApiTypes.NUMBER, description="Price the customer pays now (flash sales included)"),
    OpenApiParameter('max_price', OpenApiTypes.NUMBER),
    OpenApiParameter('in_stock', OpenApiTypes.BOOL),
    OpenApiParameter('sort', OpenApiTypes.STR, enum=list(SORT_OPTIONS)),
])
class ProductList(generics.ListAPIView):
    """Active products, 12 per page."""

    serializer_class = ProductListSerializer

    def get_queryset(self):
        products = shop_products()
        category = self.request.query_params.get('category')
        if category:
            products = products.filter(category__slug=category)
        return filter_products(products, self.request.query_params)[0]


class ProductDetail(generics.RetrieveAPIView):
    """One product with its gallery, variants (each with its own price and stock) and latest reviews."""

    serializer_class = ProductDetailSerializer
    lookup_field = 'slug'

    def get_queryset(self):
        return shop_products().prefetch_related(
            'images', Prefetch('reviews', queryset=Review.objects.select_related('user')),
        )


class ApiCart:
    """The order lines from an API request, in the shape create_order() reads from the session cart."""

    def __init__(self, items, coupon=None):
        self.cart = {}
        for line in items:
            key = make_key(line['product_id'], line.get('variant_id'))
            self.cart.setdefault(key, {'quantity': 0})['quantity'] += line['quantity']
        self.session = {'coupon_id': coupon.id} if coupon else {}


class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                   viewsets.GenericViewSet):
    """Your orders. Placing an order uses Cash on Delivery; online payment needs the website."""

    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'order_number'
    queryset = Order.objects.none()  # for the API docs; get_queryset() limits it to your orders

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related('items')

    def get_serializer_class(self):
        return OrderCreateSerializer if self.action == 'create' else OrderSerializer

    def get_throttles(self):
        if self.action == 'create':
            self.throttle_scope = 'orders'
            return [ScopedRateThrottle()]
        return super().get_throttles()

    @extend_schema(request=OrderCreateSerializer, responses={201: OrderSerializer})
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = request.user

        # Same address and phone validation as the website's checkout form.
        form = CheckoutForm({
            **{field: data.get(field, '') for field in CheckoutForm.SHIPPING_FIELDS},
            'email': data.get('email') or user.email,
            'payment_method': Order.PaymentMethod.COD,
            'gift_wrap': data['gift_wrap'], 'use_points': data['use_points'],
        }, user=user)
        if not form.is_valid():
            return Response(form.errors, status=status.HTTP_400_BAD_REQUEST)

        coupon = None
        if data.get('coupon_code'):
            coupon = Coupon.objects.filter(code__iexact=data['coupon_code'].strip()).first()
            if coupon is None:
                return Response({'coupon_code': ['This coupon does not exist.']}, status=status.HTTP_400_BAD_REQUEST)

        release_unpaid_orders()
        try:
            order = create_order(ApiCart(data['items'], coupon), form.shipping_data(), user=user,
                                 payment_method=Order.PaymentMethod.COD, gift_wrap=data['gift_wrap'],
                                 use_points=form.cleaned_data.get('use_points', False))
        except CheckoutError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        order = get_object_or_404(self.get_queryset(), pk=order.pk)
        return Response(OrderSerializer(order, context=self.get_serializer_context()).data,
                        status=status.HTTP_201_CREATED)


class ProfileView(APIView):
    """The logged-in customer: reward points and referral link."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses=ProfileSerializer)
    def get(self, request):
        user = request.user
        profile = get_profile(user)
        return Response(ProfileSerializer({
            'email': user.email, 'first_name': user.first_name, 'last_name': user.last_name,
            'points': profile.points, 'referral_code': profile.referral_code,
            'referral_url': f'{settings.SITE_URL}/?ref={profile.referral_code}',
        }).data)
