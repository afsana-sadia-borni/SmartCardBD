"""PDF invoice for an order, drawn with ReportLab (pure Python, no system libraries needed).

The built-in PDF fonts have no Taka sign, so amounts are written as "BDT 1,25,000.00".
"""
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from products.templatetags.shop_tags import lakh_group

ACCENT = colors.HexColor('#212529')
MUTED = colors.HexColor('#6c757d')


def bdt(value):
    amount = Decimal(value).quantize(Decimal('0.01'))
    sign = '-' if amount < 0 else ''
    whole, cents = f'{abs(amount):.2f}'.split('.')
    return f'{sign}BDT {lakh_group(whole)}.{cents}'


def _totals(order):
    rows = [('Subtotal', order.subtotal)]
    if order.discount:
        rows.append((f'Coupon ({order.coupon.code})' if order.coupon else 'Coupon', -order.discount))
    if order.bundle_discount:
        rows.append(('Bundle discount', -order.bundle_discount))
    if order.points_discount:
        rows.append((f'Reward points ({order.points_used})', -order.points_discount))
    if order.gift_wrap_cost:
        rows.append(('Gift wrap', order.gift_wrap_cost))
    rows.append(('Delivery', order.shipping_cost))
    return rows


def render_invoice(order):
    """Return the invoice as PDF bytes."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f'Invoice {order.order_number}', author=settings.SITE_NAME)
    styles = getSampleStyleSheet()
    normal, small = styles['Normal'], styles['Normal'].clone('small', fontSize=8.5, textColor=MUTED)
    text = lambda value: escape(str(value))  # noqa: E731 - Paragraph reads its text as markup

    created = timezone.localtime(order.created_at)
    header = Table([[
        Paragraph(f'<font size="18"><b>{text(settings.SITE_NAME)}</b></font><br/>'
                  f'<font color="#6c757d">{text(settings.SITE_URL)}</font>', normal),
        Paragraph(f'<para align="right"><font size="16"><b>INVOICE</b></font><br/>'
                  f'Order <b>{text(order.order_number)}</b><br/>{created:%d %b %Y, %I:%M %p}</para>', normal),
    ]], colWidths=['60%', '40%'])

    address = ', '.join(text(part) for part in (order.address_line, order.area, order.upazila, order.district) if part)
    parties = Table([[
        Paragraph(f'<b>Bill / ship to</b><br/>{text(order.full_name)}<br/>{text(order.phone)}<br/>'
                  f'{text(order.email)}<br/>{address}', normal),
        Paragraph(f'<para align="right"><b>Payment</b><br/>{text(order.payment_label)}<br/>'
                  f'Status: {text(order.get_payment_status_display())}<br/>'
                  f'Order status: {text(order.get_status_display())}'
                  + (f'<br/>Delivery: {text(order.delivery_estimate)}' if order.delivery_estimate else '')
                  + '</para>', normal),
    ]], colWidths=['60%', '40%'])

    item_rows = [['#', 'Item', 'Price', 'Qty', 'Amount']]
    for n, item in enumerate(order.items.all(), 1):
        name = text(item.product_title) + (f'<br/><font size="8" color="#6c757d">{text(item.variant_label)}</font>'
                                           if item.variant_label else '')
        item_rows.append([str(n), Paragraph(name, normal), bdt(item.price), str(item.quantity), bdt(item.subtotal)])
    items = Table(item_rows, colWidths=[10 * mm, None, 32 * mm, 14 * mm, 34 * mm], repeatRows=1)
    items.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), ACCENT),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('LINEBELOW', (0, -1), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))

    total_rows = [[label, bdt(amount)] for label, amount in _totals(order)]
    total_rows.append(['Total', bdt(order.total)])
    totals = Table(total_rows, colWidths=[50 * mm, 36 * mm], hAlign='RIGHT')
    totals.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 11),
        ('LINEABOVE', (0, -1), (-1, -1), 1, ACCENT),
        ('TOPPADDING', (0, -1), (-1, -1), 6),
    ]))

    story = [header, Spacer(1, 8 * mm), parties, Spacer(1, 8 * mm), items, Spacer(1, 4 * mm), totals]
    if order.note:
        story += [Spacer(1, 6 * mm), Paragraph(f'<b>Order note:</b> {text(order.note)}', normal)]
    if (order.payment_method == order.PaymentMethod.COD and order.payment_status != order.PaymentStatus.PAID
            and order.status != order.Status.CANCELLED):
        story += [Spacer(1, 6 * mm), Paragraph(f'Please pay <b>{bdt(order.total)}</b> in cash when the parcel '
                                               'arrives.', normal)]
    story += [Spacer(1, 12 * mm), Paragraph(
        f'Thank you for shopping with {text(settings.SITE_NAME)}. Returns are accepted within '
        f'{settings.RETURN_WINDOW_DAYS} days of delivery. This is a computer-generated invoice and needs no '
        'signature.', small)]
    doc.build(story)
    return buffer.getvalue()
