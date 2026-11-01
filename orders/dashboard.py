import json
from datetime import timedelta

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, F, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.utils import timezone

from products.models import Product

from .models import Order, OrderItem


@staff_member_required
def dashboard(request):
    today = timezone.localdate()
    month_start = today.replace(day=1)
    since = today - timedelta(days=29)
    valid_orders = Order.objects.exclude(status=Order.Status.CANCELLED)

    daily = {
        row['day']: row
        for row in valid_orders.filter(created_at__date__gte=since)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(revenue=Sum('total'), count=Count('id'))
    }
    days = [since + timedelta(days=i) for i in range(30)]
    sales_chart = {
        'labels': [d.strftime('%d %b') for d in days],
        'revenue': [float(daily[d]['revenue']) if d in daily else 0 for d in days],
        'orders': [daily[d]['count'] if d in daily else 0 for d in days],
    }

    status_counts = dict(Order.objects.values_list('status').annotate(c=Count('id')))
    status_chart = {
        'labels': [label for _, label in Order.Status.choices],
        'data': [status_counts.get(value, 0) for value, _ in Order.Status.choices],
    }

    top_products = (
        OrderItem.objects.exclude(order__status=Order.Status.CANCELLED)
        .values('product_title')
        .annotate(units=Sum('quantity'), revenue=Sum(F('price') * F('quantity')))
        .order_by('-units')[:5]
    )

    context = {
        'today_orders': valid_orders.filter(created_at__date=today).count(),
        'today_revenue': valid_orders.filter(created_at__date=today).aggregate(s=Sum('total'))['s'] or 0,
        'month_revenue': valid_orders.filter(created_at__date__gte=month_start).aggregate(s=Sum('total'))['s'] or 0,
        'pending_orders': Order.objects.filter(status=Order.Status.PENDING).count(),
        'total_orders': Order.objects.count(),
        'top_products': top_products,
        'low_stock': Product.objects.active().filter(stock__lte=settings.LOW_STOCK_THRESHOLD).order_by('stock')[:10],
        'recent_orders': Order.objects.all()[:8],
        'sales_chart': json.dumps(sales_chart),
        'status_chart': json.dumps(status_chart),
    }
    return render(request, 'orders/dashboard.html', context)
