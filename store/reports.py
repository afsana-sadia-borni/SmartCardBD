"""Store panel: sales reports for a date range."""
import json
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, F, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from orders.models import Order, OrderItem, ReturnRequest

from .access import store_view
from .views import render_store

RANGES = {'7': 'Last 7 days', '30': 'Last 30 days', '90': 'Last 90 days', '365': 'Last 12 months'}


def _date_range(request):
    today = timezone.localdate()
    try:
        start = date.fromisoformat(request.GET['from'])
        end = date.fromisoformat(request.GET['to'])
        if start > end or (end - start).days > 731:
            raise ValueError
        return start, end, 'custom'
    except (KeyError, ValueError):
        days = request.GET.get('days', '30')
        days = days if days in RANGES else '30'
        return today - timedelta(days=int(days) - 1), today, days


def _payment_split(orders):
    """Orders per way of paying: 'Cash on Delivery', 'bKash', ... (online orders without a channel: 'Online')."""
    counts = {}
    for row in orders.values('payment_method', 'payment_channel').annotate(n=Count('id')):
        if row['payment_method'] == Order.PaymentMethod.COD:
            label = 'Cash on Delivery'
        else:
            label = Order.PaymentChannel(row['payment_channel']).label if row['payment_channel'] else 'Online'
        counts[label] = counts.get(label, 0) + row['n']
    ordered = sorted(counts.items(), key=lambda item: -item[1])
    return {'labels': [k for k, _ in ordered], 'data': [v for _, v in ordered]}


@store_view('orders.change_order')
def reports(request):
    start, end, chosen = _date_range(request)
    placed = Order.objects.filter(created_at__date__gte=start, created_at__date__lte=end)
    sales = placed.exclude(status=Order.Status.CANCELLED)
    items = OrderItem.objects.filter(order__in=sales)

    totals = sales.aggregate(revenue=Sum('total'), orders=Count('id'), average=Avg('total'),
                             discounts=Sum(F('discount') + F('bundle_discount') + F('points_discount')))
    all_count = placed.count()
    cancelled = placed.filter(status=Order.Status.CANCELLED).count()
    returns = ReturnRequest.objects.filter(order__in=sales).count()

    days = (end - start).days + 1
    daily = {row['day']: row for row in sales.annotate(day=TruncDate('created_at')).values('day')
             .annotate(revenue=Sum('total'), count=Count('id'))}
    labels = [start + timedelta(days=i) for i in range(days)]

    def chart(rows, label_key, value_key):
        rows = list(rows)
        return {'labels': [r[label_key] or '-' for r in rows], 'data': [float(r[value_key] or 0) for r in rows]}

    context = {
        'start': start, 'end': end, 'chosen': chosen, 'ranges': RANGES,
        'revenue': totals['revenue'] or 0, 'order_count': totals['orders'], 'average': totals['average'] or 0,
        'discounts': totals['discounts'] or 0, 'units': items.aggregate(n=Sum('quantity'))['n'] or 0,
        'new_customers': get_user_model().objects.filter(is_staff=False, date_joined__date__gte=start,
                                                         date_joined__date__lte=end).count(),
        'cancel_rate': round(cancelled / all_count * 100, 1) if all_count else 0,
        'return_rate': round(returns / totals['orders'] * 100, 1) if totals['orders'] else 0,
        'charts': json.dumps({
            'daily': {'labels': [d.strftime('%d %b') for d in labels],
                      'revenue': [float(daily[d]['revenue']) if d in daily else 0 for d in labels],
                      'orders': [daily[d]['count'] if d in daily else 0 for d in labels]},
            'category': chart(items.values('product__category__name').annotate(v=Sum(F('price') * F('quantity')))
                              .order_by('-v')[:8], 'product__category__name', 'v'),
            'district': chart(sales.values('district').annotate(v=Count('id')).order_by('-v')[:10], 'district', 'v'),
            'payment': _payment_split(sales),
        }),
        'top_products': items.values('product_title').annotate(units=Sum('quantity'),
                                                               revenue=Sum(F('price') * F('quantity'))).order_by('-revenue')[:10],
        'top_customers': sales.values('full_name', 'phone').annotate(orders=Count('id'), spent=Sum('total'))
                         .order_by('-spent')[:10],
        'csv_days': days,
    }
    return render_store(request, 'store/reports.html', context, section='store:reports')
