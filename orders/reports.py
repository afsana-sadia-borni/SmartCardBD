import csv
from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.utils import timezone

from .models import Order

CSV_COLUMNS = [
    ('Order', 'order_number'), ('Date', 'created_at'), ('Customer', 'full_name'), ('Phone', 'phone'),
    ('Email', 'email'), ('District', 'district'), ('Status', 'status'), ('Payment', 'payment_method'),
    ('Paid', 'payment_status'), ('Items', 'item_count'), ('Subtotal', 'subtotal'), ('Discount', 'discount'),
    ('Bundle discount', 'bundle_discount'), ('Points discount', 'points_discount'),
    ('Shipping', 'shipping_cost'), ('Gift wrap', 'gift_wrap_cost'), ('Total', 'total'),
]


def orders_csv_response(orders, filename):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('﻿')  # BOM so Excel opens Bangla/৳ text correctly
    writer = csv.writer(response)
    writer.writerow([label for label, _ in CSV_COLUMNS])
    for order in orders.prefetch_related('items'):
        row = []
        for _, attr in CSV_COLUMNS:
            value = getattr(order, attr)
            if attr == 'created_at':
                value = timezone.localtime(value).strftime('%Y-%m-%d %H:%M')
            row.append(value)
        writer.writerow(row)
    return response


@staff_member_required
def sales_report_csv(request):
    days = min(max(int(request.GET.get('days', 30) or 30), 1), 366)
    since = timezone.now() - timedelta(days=days)
    orders = Order.objects.filter(created_at__gte=since).order_by('created_at')
    return orders_csv_response(orders, f'sales-last-{days}-days-{timezone.localdate():%Y%m%d}.csv')
