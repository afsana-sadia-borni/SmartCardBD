"""Products to and from CSV (Excel and Google Sheets can open and save it)."""
import csv
import io
from decimal import Decimal, InvalidOperation

from django.db import transaction

from products.models import Category, Product

COLUMNS = ['slug', 'title', 'category', 'brand', 'price', 'sale_price', 'stock', 'is_active', 'is_featured',
           'description']
REQUIRED = ['title', 'category', 'price']
MAX_ROWS = 2000
TRUE = {'1', 'yes', 'true', 'y', 'on'}


def export_products_csv(response):
    response.write('﻿')  # BOM, so Excel reads Bangla text correctly
    writer = csv.writer(response)
    writer.writerow(COLUMNS)
    for p in Product.objects.select_related('category').order_by('category__name', 'title'):
        writer.writerow([p.slug, p.title, p.category.name, p.brand, p.price, p.discount_price or '', p.stock,
                         'yes' if p.is_active else 'no', 'yes' if p.is_featured else 'no', p.description])
    return response


def _decimal(value, field, required=False):
    value = (value or '').strip().replace(',', '').replace('৳', '')
    if not value:
        if required:
            raise ValueError(f'{field} is required')
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError(f'{field} "{value}" is not a number') from None
    if number < 0:
        raise ValueError(f'{field} can\'t be negative')
    return number


def import_products_csv(file, dry_run=False):
    """Create or update products from an uploaded CSV. All or nothing: any bad row and nothing is saved.

    Returns (created, updated, errors) where errors is a list of (row number, message).
    """
    try:
        text = file.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        return 0, 0, [(0, 'The file must be saved as CSV UTF-8.')]
    reader = csv.DictReader(io.StringIO(text))
    headers = [h.strip().lower() for h in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED if c not in headers]
    if missing:
        return 0, 0, [(1, f'Missing column(s): {", ".join(missing)}')]
    created = updated = 0
    errors = []
    with transaction.atomic():
        for number, raw in enumerate(reader, start=2):
            if number > MAX_ROWS + 1:
                errors.append((number, f'Only {MAX_ROWS} rows per file.'))
                break
            row = {(k or '').strip().lower(): (v or '').strip() for k, v in raw.items()}
            if not any(row.values()):
                continue
            try:
                title = row.get('title') or ''
                if not title:
                    raise ValueError('title is required')
                if not row.get('category'):
                    raise ValueError('category is required')
                price = _decimal(row.get('price'), 'price', required=True)
                sale = _decimal(row.get('sale_price'), 'sale_price')
                if sale is not None and sale >= price:
                    raise ValueError('sale_price must be lower than price')
                stock = row.get('stock') or '0'
                if not stock.isdigit():
                    raise ValueError(f'stock "{stock}" must be a whole number')
                category, _ = Category.objects.get_or_create(name=row['category'])
                product = Product.objects.filter(slug=row['slug']).first() if row.get('slug') else None
                is_new = product is None
                product = product or Product(description='')
                product.title, product.category, product.brand = title[:200], category, row.get('brand', '')[:100]
                product.price, product.discount_price, product.stock = price, sale, int(stock)
                if row.get('description'):
                    product.description = row['description']
                if row.get('is_active'):
                    product.is_active = row['is_active'].lower() in TRUE
                if row.get('is_featured'):
                    product.is_featured = row['is_featured'].lower() in TRUE
                product.save()
                created += is_new
                updated += not is_new
            except ValueError as exc:
                errors.append((number, str(exc)))
        if errors or dry_run:
            transaction.set_rollback(True)
    return created, updated, errors
