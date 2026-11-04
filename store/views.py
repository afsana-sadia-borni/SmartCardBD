import json
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from orders.models import BlockedPhone, Order, OrderItem, ReturnRequest
from orders.courier import CourierError, book_steadfast, cod_amount, steadfast_enabled
from orders.services import CheckoutError, cancel_order
from products.models import Product, Question

from .access import NAV, can, store_view
from .forms import TeamMemberForm, TrackingForm
from .roles import ROLES, role_of

PER_PAGE = 20


def render_store(request, template, context=None, section=''):
    """Render a store panel page: adds the sidebar (only sections this person may use) and badges."""
    user = request.user
    badges = {
        'store:orders': Order.objects.filter(status=Order.Status.PENDING).count(),
        'store:returns': ReturnRequest.objects.filter(status=ReturnRequest.Status.PENDING).count(),
        'store:questions': Question.objects.filter(answered_at__isnull=True).count(),
    }
    nav = []
    for heading, items in NAV:
        links = [{'name': name, 'label': label, 'icon': icon, 'url': reverse(name), 'badge': badges.get(name, 0),
                  'active': name == section}
                 for name, label, icon, perm in items if can(user, perm)]
        if links:
            nav.append((heading, links))
    return render(request, template, {
        'store_nav': nav, 'section': section, 'role': role_of(user),
        'can_orders': can(user, 'orders.change_order'),
        **(context or {}),
    })


def redirect_back(request, default):
    """Back to the page the form was on (?next=), only if it is on this site."""
    next_url = request.POST.get('next')
    if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}, request.is_secure()):
        return redirect(next_url)
    return redirect(default)


def paginate(request, queryset):
    return Paginator(queryset, PER_PAGE).get_page(request.GET.get('page'))


# ---------- Dashboard ----------

@store_view()
def dashboard(request):
    today = timezone.localdate()
    since = today - timedelta(days=29)
    valid = Order.objects.exclude(status=Order.Status.CANCELLED)

    daily = {
        row['day']: row
        for row in valid.filter(created_at__date__gte=since).annotate(day=TruncDate('created_at'))
        .values('day').annotate(revenue=Sum('total'), count=Count('id'))
    }
    days = [since + timedelta(days=i) for i in range(30)]
    sales_chart = {
        'labels': [d.strftime('%d %b') for d in days],
        'revenue': [float(daily[d]['revenue']) if d in daily else 0 for d in days],
        'orders': [daily[d]['count'] if d in daily else 0 for d in days],
    }
    status_counts = dict(Order.objects.values_list('status').annotate(c=Count('id')))
    status_chart = {
        'labels': [str(label) for _value, label in Order.Status.choices],
        'data': [status_counts.get(value, 0) for value, _ in Order.Status.choices],
    }
    low_stock = Product.objects.active().filter(stock__lte=settings.LOW_STOCK_THRESHOLD)
    return render_store(request, 'store/dashboard.html', {
        'today_orders': valid.filter(created_at__date=today).count(),
        'today_revenue': valid.filter(created_at__date=today).aggregate(s=Sum('total'))['s'] or 0,
        'month_revenue': valid.filter(created_at__date__gte=today.replace(day=1)).aggregate(s=Sum('total'))['s'] or 0,
        'customer_count': get_user_model().objects.filter(is_staff=False).count(),
        'pending_orders': status_counts.get(Order.Status.PENDING, 0),
        'to_ship': status_counts.get(Order.Status.CONFIRMED, 0),
        'pending_returns': ReturnRequest.objects.filter(status=ReturnRequest.Status.PENDING).count(),
        'unanswered_questions': Question.objects.filter(answered_at__isnull=True).count(),
        'low_stock_count': low_stock.count(),
        'low_stock': low_stock.order_by('stock')[:6],
        'top_products': (
            OrderItem.objects.exclude(order__status=Order.Status.CANCELLED).values('product_title')
            .annotate(units=Sum('quantity'), revenue=Sum(F('price') * F('quantity'))).order_by('-units')[:5]
        ),
        'recent_orders': Order.objects.all()[:6],
        'sales_chart': json.dumps(sales_chart),
        'status_chart': json.dumps(status_chart),
    }, section='store:dashboard')


# ---------- Orders ----------

ORDER_TABS = [
    ('pending', 'New'), ('confirmed', 'To ship'), ('shipped', 'Shipped'), ('delivered', 'Delivered'),
    ('cancelled', 'Cancelled'), ('all', 'All'),
]

# action: (allowed current statuses, new status, button label)
ORDER_ACTIONS = {
    'confirm': ({Order.Status.PENDING}, Order.Status.CONFIRMED),
    'ship': ({Order.Status.PENDING, Order.Status.CONFIRMED}, Order.Status.SHIPPED),
    'deliver': ({Order.Status.SHIPPED}, Order.Status.DELIVERED),
}


@store_view('orders.change_order')
def order_list(request):
    tab = request.GET.get('status', 'all')
    if tab not in dict(ORDER_TABS):
        tab = 'all'
    orders = Order.objects.annotate(items_count=Sum('items__quantity'))
    q = request.GET.get('q', '').strip()
    if q:
        orders = orders.filter(Q(order_number__icontains=q) | Q(full_name__icontains=q) | Q(phone__icontains=q)
                               | Q(email__icontains=q))
    customer = request.GET.get('customer')
    if customer and customer.isdigit():
        orders = orders.filter(user_id=customer)
    counts = dict(orders.order_by().values_list('status').annotate(c=Count('id')))
    if tab != 'all':
        orders = orders.filter(status=tab)
    tabs = [(key, label, sum(counts.values()) if key == 'all' else counts.get(key, 0)) for key, label in ORDER_TABS]
    return render_store(request, 'store/orders/list.html', {
        'page_obj': paginate(request, orders), 'tabs': tabs, 'tab': tab, 'q': q, 'customer': customer,
        'steadfast': steadfast_enabled(),
    }, section='store:orders')


def _timeline(order):
    """Status changes from the order's history: [(when, status label, who)]."""
    events, previous = [], None
    labels = dict(Order.Status.choices)
    for record in order.history.order_by('history_date', 'history_id').select_related('history_user'):
        if record.status != previous:
            who = record.history_user.get_full_name() or record.history_user.email if record.history_user else ''
            events.append((record.history_date, labels.get(record.status, record.status), who))
            previous = record.status
    return events


@store_view('orders.change_order')
def order_detail(request, order_number):
    order = get_object_or_404(Order.objects.prefetch_related('items__product').select_related('user', 'coupon'),
                              order_number=order_number)
    actions = [name for name, (allowed, _) in ORDER_ACTIONS.items() if order.status in allowed]
    return render_store(request, 'store/orders/detail.html', {
        'order': order, 'actions': actions, 'timeline': _timeline(order),
        'can_cancel': order.status not in (Order.Status.DELIVERED, Order.Status.CANCELLED),
        'return_request': getattr(order, 'return_request', None),
        'whatsapp': '88' + order.phone if order.phone.startswith('01') else order.phone,
        'steadfast': steadfast_enabled(), 'cod_amount': cod_amount(order),
        'phone_blocked': BlockedPhone.objects.filter(phone=order.phone).exists(),
        'phone_history': Order.objects.filter(phone=order.phone).exclude(pk=order.pk).values('status')
        .annotate(n=Count('id')).order_by('status'),
        'tracking_form': TrackingForm(initial={'courier_name': order.courier_name or 'Pathao',
                                               'tracking_code': order.courier_tracking_code,
                                               'tracking_link': order.courier_tracking_link}),
    }, section='store:orders')


@require_POST
@store_view('orders.change_order')
def order_action(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    action = request.POST.get('action')
    if action == 'book_steadfast':
        try:
            order = book_steadfast(order)
            messages.success(request, f'Booked with Steadfast: tracking {order.courier_tracking_code}. '
                                      'The order is now Shipped and the customer has the tracking link.')
        except CourierError as exc:
            messages.error(request, str(exc))
        return redirect('store:order_detail', order.order_number)
    if action == 'set_tracking':
        form = TrackingForm(request.POST)
        if form.is_valid():
            order.courier_name = form.cleaned_data['courier_name']
            order.courier_tracking_code = form.cleaned_data['tracking_code']
            order.courier_tracking_link = form.cleaned_data['tracking_link']
            order.save(update_fields=['courier_name', 'courier_tracking_code', 'courier_tracking_link', 'updated_at'])
            messages.success(request, 'Tracking details saved.')
        else:
            messages.error(request, 'Enter the courier name and a tracking code or link.')
        return redirect('store:order_detail', order.order_number)
    if action in ('block_phone', 'unblock_phone'):
        if action == 'block_phone':
            BlockedPhone.objects.get_or_create(phone=order.phone, defaults={
                'reason': f'Blocked from order {order.order_number}', 'created_by': request.user})
            messages.success(request, f'{order.phone} can no longer use Cash on Delivery.')
        else:
            BlockedPhone.objects.filter(phone=order.phone).delete()
            messages.success(request, f'{order.phone} can use Cash on Delivery again.')
        return redirect('store:order_detail', order.order_number)
    if action == 'cancel':
        try:
            cancel_order(order, by_staff=True)
            messages.success(request, f'Order {order.order_number} cancelled. Items are back in stock.')
        except CheckoutError as exc:
            messages.error(request, str(exc))
        return redirect('store:order_detail', order.order_number)

    if action not in ORDER_ACTIONS:
        messages.error(request, 'Unknown action.')
        return redirect('store:order_detail', order.order_number)
    # Signals email/text the customer (and mark Cash on Delivery orders paid on delivery).
    if not _change_status(order, action):
        order.refresh_from_db()
        messages.error(request, f'This order is already {order.get_status_display().lower()}.')
        return redirect('store:order_detail', order.order_number)
    order.refresh_from_db()
    messages.success(request, f'Order {order.order_number} is now {order.get_status_display()}. '
                              'The customer has been notified.')
    return redirect('store:order_detail', order.order_number)


def _change_status(order, action):
    """Apply a Confirm / Ship / Deliver action if the order's current status allows it. Returns True if done."""
    allowed, new_status = ORDER_ACTIONS[action]
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status not in allowed:
            return False
        order.status = new_status
        order.save(update_fields=['status', 'updated_at'])
    return True


@require_POST
@store_view('orders.change_order')
def orders_bulk(request):
    """The action bar on the orders list: confirm, ship, deliver, book Steadfast or print slips for many orders."""
    numbers = request.POST.getlist('orders')[:200]
    action = request.POST.get('action')
    orders = list(Order.objects.filter(order_number__in=numbers))
    if not orders:
        messages.error(request, 'Select at least one order.')
        return redirect_back(request, 'store:orders')
    if action == 'slips':
        query = '&'.join(f'o={o.order_number}' for o in orders)
        return redirect(f"{reverse('store:packing_slips')}?{query}")
    done, problems = 0, []
    for order in orders:
        if action in ORDER_ACTIONS:
            if _change_status(order, action):
                done += 1
            else:
                problems.append(f'{order.order_number} is {order.get_status_display().lower()}')
        elif action == 'book_steadfast':
            try:
                book_steadfast(order)
                done += 1
            except CourierError as exc:
                problems.append(f'{order.order_number}: {exc}')
        else:
            messages.error(request, 'Unknown action.')
            return redirect_back(request, 'store:orders')
    if done:
        messages.success(request, f'{done} order{"s" if done != 1 else ""} updated. Customers have been notified.')
    if problems:
        messages.warning(request, 'Skipped: ' + '; '.join(problems[:10]) + (' ...' if len(problems) > 10 else ''))
    return redirect_back(request, 'store:orders')


@store_view('orders.change_order')
def packing_slips(request):
    """Printable packing slips, one per page, for the selected orders."""
    numbers = request.GET.getlist('o')[:200]
    orders = Order.objects.filter(order_number__in=numbers).prefetch_related('items').order_by('created_at')
    return render(request, 'store/orders/slips.html', {
        'orders': [(order, cod_amount(order)) for order in orders], 'site_name': settings.SITE_NAME,
    })


# ---------- Customers ----------

@store_view('auth.view_user')
def customer_list(request):
    customers = (
        get_user_model().objects.filter(is_staff=False).select_related('profile')
        .annotate(order_count=Count('orders', distinct=True),
                  spent=Sum('orders__total', filter=~Q(orders__status=Order.Status.CANCELLED)))
        .order_by('-date_joined')
    )
    q = request.GET.get('q', '').strip()
    if q:
        customers = customers.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
    return render_store(request, 'store/customers.html', {'page_obj': paginate(request, customers), 'q': q},
                        section='store:customers')


# ---------- Team (owner only) ----------

@store_view('superuser')
def team(request):
    User = get_user_model()
    form = TeamMemberForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        member = form.user
        member.is_staff = True
        member.save(update_fields=['is_staff'])
        member.groups.remove(*Group.objects.filter(name__in=ROLES))
        member.groups.add(Group.objects.get(name=form.cleaned_data['role']))
        messages.success(request, f'{member.email} is now a {form.cleaned_data["role"]}. They will see the '
                                  'store panel next time they log in.')
        return redirect('store:team')
    members = User.objects.filter(is_staff=True).prefetch_related('groups').order_by('-is_superuser', 'email')
    return render_store(request, 'store/team.html', {
        'form': form, 'members': [(m, role_of(m)) for m in members], 'roles': ROLES,
    }, section='store:team')


@require_POST
@store_view('superuser')
def team_remove(request, user_id):
    member = get_object_or_404(get_user_model(), pk=user_id, is_staff=True)
    if member.is_superuser:
        messages.error(request, "Owner accounts can't be removed here.")
    else:
        member.is_staff = False
        member.save(update_fields=['is_staff'])
        member.groups.remove(*Group.objects.filter(name__in=ROLES))
        messages.success(request, f'{member.email} no longer has access to the store panel.')
    return redirect('store:team')


# ---------- Integrations (owner only) ----------

def _integration_status():
    """What is set up, from settings. Secrets themselves are never shown."""
    from accounts.push import push_enabled
    from core.sms import sms_enabled
    from orders.payments import is_configured as payments_configured

    email_on = settings.EMAIL_BACKEND.endswith('smtp.EmailBackend')
    return [
        {'name': 'Email (SMTP)', 'icon': 'envelope', 'on': email_on,
         'detail': f'Sending through {settings.EMAIL_HOST}' if email_on else 'Emails are only printed in the server log.',
         'env': 'EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, DEFAULT_FROM_EMAIL', 'test': 'email'},
        {'name': 'SMS (BulkSMSBD)', 'icon': 'chat-dots', 'on': sms_enabled(),
         'detail': 'Order texts and sign-up codes are sent.' if sms_enabled() else 'Texts are only written to the log.',
         'env': 'SMS_API_KEY, SMS_SENDER_ID', 'test': 'sms'},
        {'name': 'Online payments (SSLCommerz)', 'icon': 'credit-card', 'on': payments_configured(),
         'detail': ('SANDBOX: test money only.' if settings.SSLCOMMERZ_SANDBOX else 'LIVE: real payments.')
                   if payments_configured() else 'Only Cash on Delivery is offered.',
         'env': 'SSLCOMMERZ_STORE_ID, SSLCOMMERZ_STORE_PASSWORD, SSLCOMMERZ_SANDBOX', 'warn': settings.SSLCOMMERZ_SANDBOX},
        {'name': 'Courier (Steadfast)', 'icon': 'truck', 'on': steadfast_enabled(),
         'detail': 'Book parcels from the order page.' if steadfast_enabled() else 'Tracking can still be added by hand.',
         'env': 'STEADFAST_API_KEY, STEADFAST_SECRET_KEY'},
        {'name': 'Background jobs (Celery + Redis)', 'icon': 'cpu', 'on': not settings.CELERY_TASK_ALWAYS_EAGER,
         'detail': 'Emails, texts and scheduled jobs run in the worker.' if not settings.CELERY_TASK_ALWAYS_EAGER
                   else 'Jobs run inside web requests; scheduled jobs need cron.', 'env': 'REDIS_URL'},
        {'name': 'Error monitoring (Sentry)', 'icon': 'bug', 'on': bool(settings.SENTRY_DSN),
         'detail': 'Errors are reported to Sentry.' if settings.SENTRY_DSN else 'Errors only appear in the server log.',
         'env': 'SENTRY_DSN'},
        {'name': 'Push notifications', 'icon': 'bell', 'on': push_enabled(),
         'detail': 'Customers can turn them on.' if push_enabled() else 'Off.',
         'env': 'VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY (python manage.py generate_vapid_keys)'},
    ]


@store_view('superuser')
def integrations(request):
    if request.method == 'POST':
        from core.sms import SMSError, send_sms
        from django.core.mail import send_mail

        if request.POST.get('test') == 'email':
            try:
                send_mail(f'{settings.SITE_NAME} test email', 'Email sending works.', None, [request.user.email])
                messages.success(request, f'Test email sent to {request.user.email}.')
            except Exception as exc:  # noqa: BLE001 - show the SMTP problem to the owner
                messages.error(request, f'Email failed: {exc}')
        elif request.POST.get('test') == 'sms':
            phone = request.POST.get('phone', '')
            try:
                result = send_sms(phone, f'{settings.SITE_NAME}: SMS sending works.')
                messages.success(request, 'Test SMS sent.' if result == 'sent' else 'No SMS provider: written to the log.')
            except SMSError as exc:
                messages.error(request, f'SMS failed: {exc}')
        return redirect('store:integrations')
    return render_store(request, 'store/integrations.html', {'services': _integration_status()},
                        section='store:integrations')
