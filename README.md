# SmartCart BD

A full-featured e-commerce web app for the Bangladeshi market, built with Django.
Customers can browse and search products, check out as a guest or with an account, pay
cash on delivery or online through SSLCommerz (bKash, Nagad, cards), and track their orders.
Staff manage the store from the Django admin and a sales dashboard.

## Features

**Shopping**
- Product catalogue with categories, brands, sale prices and stock levels
- Search, filters (category, price range, brand, in stock) and sorting, with pagination
- SEO-friendly slug URLs (`/product/samsung-galaxy-a15/`); old `/product/<id>/` links redirect permanently
- AJAX cart: add, change quantity, remove, no page reloads; quantities are capped at available stock
- Coupons: percentage or flat, with minimum order, maximum discount, validity window and usage limit
- Recommendations: "You may also like" (TF-IDF content similarity) and "Frequently bought together" (order co-occurrence)

**Checkout & orders**
- Guest checkout, or logged-in checkout with saved addresses
- Bangladesh-specific: all 64 districts, phone validation (`01XXXXXXXXX`), shipping charged by zone (inside/outside Dhaka) with free delivery over a threshold
- Cash on Delivery and SSLCommerz online payment (server-side validation and IPN)
- Order confirmation and status-update emails
- Order tracking timeline, order history, customer cancellation (restocks items)
- Abandoned online payments are cancelled after `UNPAID_ORDER_TIMEOUT_MINUTES` (default 60) so their stock goes back on sale; a payment that arrives late revives the order if stock is still available, otherwise it is flagged for refund

**Accounts**
- Email sign-up/login, password reset and optional Google login (django-allauth)
- Address book with a default address
- Wishlist
- Verified-purchase reviews and ratings (only for delivered orders)

**Layout**
- Every page (including 404/500) shares a top bar (search, cart, account) and a sidebar
  (shop links, categories, account). On phones the sidebar becomes a slide-out menu.

**Store management**
- Django admin for products, orders, coupons, reviews and addresses, with bulk order status actions
- Sales dashboard (`/dashboard/`): revenue and orders for the last 30 days, orders by status, top products, low-stock alerts

## Engineering notes

- **No overselling.** `orders/services.py::create_order` locks the product rows with `SELECT ... FOR UPDATE` inside a transaction, re-checks stock, and decrements it with `F()` expressions. If two customers try to buy the last unit at the same moment, only one order succeeds.
- **Prices are never trusted from the client or session.** The cart stores only product ids and quantities. Prices are read from the database at checkout, and each `OrderItem` keeps a snapshot of the title and price paid.
- **Payments are verified server to server.** A success redirect from the gateway is not enough on its own. Every payment is re-validated with the SSLCommerz validation API (status, transaction id, amount and currency must match), and `mark_order_paid` is idempotent, so the success callback and the IPN can both arrive safely.
- **Business logic lives in services**, not views (`orders/services.py`, `orders/payments.py`, `recommendations/engine.py`), which keeps views thin and the logic testable.
- **Configuration is read from the environment** (`.env`). No secrets are kept in the code.

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, Django 6.1 |
| Auth | django-allauth |
| Database | SQLite locally, PostgreSQL (e.g. Neon) via `DATABASE_URL` |
| Frontend | Django templates, Bootstrap 5.3, Bootstrap Icons, vanilla JS (fetch) |
| Production | gunicorn, WhiteNoise (static files), django-storages (S3/R2 for uploads) |
| Charts | Chart.js |
| Payments | SSLCommerz v4 API |
| ML | scikit-learn (TF-IDF + cosine similarity) |
| Tests | Django test framework (72 tests) |

## Getting started

```bash
git clone <repo-url> && cd SmartcardBD
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then set SECRET_KEY (DEBUG=True is fine locally)
python manage.py migrate
python manage.py seed_demo    # demo categories, 17 products and coupon WELCOME10
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000. The admin is at `/admin/` and the sales dashboard at `/dashboard/`.

Without `EMAIL_HOST`, emails (order confirmations, password resets) are printed to the terminal.

### Online payments (optional)

1. Create a free sandbox store at https://developer.sslcommerz.com/registration/
2. Put the store ID and password in `.env` (`SSLCOMMERZ_STORE_ID`, `SSLCOMMERZ_STORE_PASSWORD`).
3. The "Online Payment" option appears at checkout automatically.

The IPN callback must be reachable from the internet. Locally, the success redirect still validates and confirms the payment.

Unpaid online orders are released automatically whenever someone checks out. In production you can also
run `python manage.py release_unpaid_orders` from a cron job (for example every 15 minutes).

### Google login (optional)

Create an OAuth client in Google Cloud Console with the redirect URI
`http://localhost:8000/accounts/google/login/callback/`, then set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.

## Running tests

```bash
python manage.py test
```

The tests cover the cart (stock caps, price changes, safe redirects), coupons, checkout (totals,
shipping, stock that runs out between cart and checkout, price snapshots), order access control,
cancellation and restocking, SSLCommerz validation (including amount tampering and idempotent IPN),
addresses, wishlist, reviews, search and filters, recommendations, the shared layout and
error pages, and production settings (`check --deploy`).

## Project structure

```
accounts/         Address book, wishlist, BD districts & phone validation
cart/             Session cart (cart.py), AJAX cart and coupon views
orders/           Order & Coupon models, checkout, services (stock locking),
                  SSLCommerz integration, admin, dashboard, emails
products/         Catalogue, search/filter, reviews, seed_demo command, template tags
recommendations/  TF-IDF similar products, frequently-bought-together
templates/        Base layout, shared partials, django-allauth overrides
static/           CSS, JS, images
config/           Settings, root URLs, layout/error-page/settings tests
```

## Deploying

1. Set these environment variables on the host (never commit them):
   `DEBUG=False`, a new `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` and `DATABASE_URL`.
2. Build: `pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate`
3. Start: `gunicorn config.wsgi` (already in the `Procfile`).

Static files (CSS/JS) are served by WhiteNoise, so no separate web server is needed.
HTTPS redirect and HSTS are on by default when `DEBUG=False`; `SECURE_HSTS_SECONDS` starts at
one hour, raise it to `31536000` once HTTPS works on your domain.

**Product images.** Hosts such as Render and Railway erase the local disk on every deploy, so
uploaded images would disappear. Create an S3-compatible bucket (Cloudflare R2 has a free tier)
and set `AWS_STORAGE_BUCKET_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
`AWS_S3_ENDPOINT_URL` and `AWS_S3_CUSTOM_DOMAIN` (see `.env.example`). On a VPS with a
persistent disk you can leave these empty and let nginx serve `media/`.
