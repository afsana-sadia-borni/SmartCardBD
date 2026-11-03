from datetime import datetime

from django.conf import settings
from django.urls import reverse
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from accounts.constants import DISTRICT_CHOICES
from orders.models import Order, OrderItem
from products.images import webp_url
from products.models import Category, Product, ProductVariant, Review


def absolute(request, url):
    if not url:
        return None
    return request.build_absolute_uri(url) if request is not None and url.startswith('/') else url


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Log in with email + password (the site has no usernames)."""

    username_field = 'email'


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug']


class ProductListSerializer(serializers.ModelSerializer):
    category = serializers.CharField(source='category.name')
    final_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    discount_percent = serializers.IntegerField(read_only=True)
    in_stock = serializers.BooleanField(read_only=True)
    rating = serializers.SerializerMethodField()
    review_count = serializers.IntegerField(read_only=True)
    sold = serializers.IntegerField(read_only=True)
    flash_sale_ends_at = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    thumbnail = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['id', 'slug', 'title', 'brand', 'category', 'price', 'final_price', 'discount_percent', 'stock',
                  'in_stock', 'rating', 'review_count', 'sold', 'flash_sale_ends_at', 'image', 'thumbnail', 'url']

    def get_rating(self, product) -> float | None:
        rating = getattr(product, 'avg_rating', None)
        return round(rating, 1) if rating else None

    def get_flash_sale_ends_at(self, product) -> datetime | None:
        return product.flash_sale[1] if product.flash_sale else None

    def get_image(self, product) -> str | None:
        return absolute(self.context.get('request'), product.image.url if product.image else None)

    def get_thumbnail(self, product) -> str | None:
        """400px WebP copy, for lists on mobile."""
        return absolute(self.context.get('request'), webp_url(product.image.url, 400) if product.image else None)

    def get_url(self, product) -> str:
        return absolute(self.context.get('request'), product.get_absolute_url())


class VariantSerializer(serializers.ModelSerializer):
    label = serializers.CharField(read_only=True)
    price = serializers.DecimalField(source='regular_price', max_digits=10, decimal_places=2, read_only=True)
    final_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    in_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = ProductVariant
        fields = ['id', 'label', 'color', 'size', 'storage', 'sku', 'price', 'final_price', 'stock', 'in_stock']


class ReviewSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ['rating', 'comment', 'author', 'created_at']

    def get_author(self, review) -> str:
        # First name only (or the start of the email) - never the full email address.
        return review.user.first_name or review.user.email.split('@')[0][:3] + '***'


class ImageSerializer(serializers.Serializer):
    url = serializers.CharField()
    alt = serializers.CharField()
    color = serializers.CharField()


class ProductDetailSerializer(ProductListSerializer):
    images = serializers.SerializerMethodField()
    variants = VariantSerializer(source='active_variants', many=True, read_only=True)
    reviews = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + ['description', 'images', 'variants', 'reviews']

    @extend_schema_field(ImageSerializer(many=True))
    def get_images(self, product):
        request = self.context.get('request')
        return [{'url': absolute(request, img['url']), 'alt': img['alt'], 'color': img['color']}
                for img in product.gallery]

    @extend_schema_field(ReviewSerializer(many=True))
    def get_reviews(self, product):
        return ReviewSerializer(product.reviews.all()[:10], many=True).data


class OrderItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ['product_id', 'variant_id', 'product_title', 'variant_label', 'price', 'quantity', 'subtotal']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    invoice_url = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ['order_number', 'status', 'status_display', 'created_at', 'payment_method', 'payment_channel', 'payment_status',
                  'full_name', 'email', 'phone', 'district', 'upazila', 'area', 'address_line', 'note',
                  'gift_wrap', 'delivery_estimate', 'items', 'subtotal', 'discount', 'bundle_discount',
                  'points_used', 'points_discount', 'gift_wrap_cost', 'shipping_cost', 'total', 'invoice_url']

    def get_invoice_url(self, order) -> str:
        return absolute(self.context.get('request'), reverse('order_invoice', args=[order.order_number]))


class OrderLineSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(min_value=1)
    variant_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1, max_value=20)


class OrderCreateSerializer(serializers.Serializer):
    """Place a Cash on Delivery order. Prices, stock, coupons and delivery are checked on the
    server exactly as on the website's checkout."""

    items = OrderLineSerializer(many=True, allow_empty=False, max_length=50)
    full_name = serializers.CharField(max_length=100)
    email = serializers.EmailField(required=False, help_text="Defaults to the account's email.")
    phone = serializers.CharField(max_length=15, help_text='Bangladeshi mobile number, e.g. 01712345678')
    district = serializers.ChoiceField(choices=DISTRICT_CHOICES)
    upazila = serializers.CharField(max_length=60)
    area = serializers.CharField(max_length=100)
    address_line = serializers.CharField(max_length=255)
    note = serializers.CharField(required=False, allow_blank=True, default='')
    gift_wrap = serializers.BooleanField(required=False, default=False,
                                         help_text=f'Adds ৳{settings.GIFT_WRAP_PRICE}.')
    use_points = serializers.BooleanField(required=False, default=False)
    coupon_code = serializers.CharField(required=False, allow_blank=True, max_length=30)


class ProfileSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    points = serializers.IntegerField()
    referral_code = serializers.CharField()
    referral_url = serializers.CharField()
