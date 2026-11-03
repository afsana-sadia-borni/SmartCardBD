# SmartCart BD

A full-featured e-commerce web app for the Bangladeshi market, built with Django.
Customers can browse and search products, check out as a guest or with an account, pay
cash on delivery or online through SSLCommerz (bKash, Nagad, cards), and track their orders.
Staff manage the store from the Django admin and a sales dashboard.

## Features

**Shopping**
- Product catalogue with categories, brands, sale prices and stock levels
- Product variants (size, colour, storage) with their own price, stock and SKU; picking a colour shows its photo
- Image gallery with hover zoom, quick-view popup, live search suggestions (debounced, keyboard friendly)
- Slide-out mini cart (AJAX add to cart), infinite scroll with skeleton loading, compare up to 4 products
- Flash sales with a live countdown (prices return to normal automatically), bundle offers, real "sold" counts
- Product Q&A (staff answer from the admin), review photos, "notify me if the price drops" alerts
- Search, filters (category, price range, brand, in stock) and sorting, with pagination
- SEO-friendly slug URLs (`/product/samsung-galaxy-a15/`); old `/product/<id>/` links redirect permanently
- AJAX cart: add, change quantity, remove, no page reloads; quantities are capped at available stock
- Coupons: percentage or flat, with minimum order, maximum discount, validity window and usage limit
- Recommendations: "You may also like" (TF-IDF content similarity) and "Frequently bought together" (order co-occurrence)

**Checkout & orders**
- Guest checkout, or logged-in checkout with saved addresses
- Bangladesh-specific: Division → District → Upazila/Thana dropdowns (all 64 districts, Dhaka city thanas), phone validation (`01XXXXXXXXX`), delivery charge and delivery time per zone (editable in the admin), free delivery over a threshold
- Order tracking without an account (`/track/`: order number + phone), gift wrap, order notes
- Return / refund requests within 7 days of delivery (with a photo); staff approve or reject in the admin
- Cash on Delivery and SSLCommerz online payment (server-side validation and IPN)
- Order confirmation and status-update emails
- Order tracking timeline, order history, customer cancellation (restocks items)
- Abandoned online payments are cancelled after `UNPAID_ORDER_TIMEOUT_MINUTES` (default 60) so their stock goes back on sale; a payment that arrives late revives the order if stock is still available, otherwise it is flagged for refund

**Accounts**
- Email sign-up/login, password reset and optional Google login (django-allauth)
- Address book with a default address
- Wishlist
- Verified-purchase reviews and ratings (only for delivered orders)
- Reward points (1 point per ৳100, 100 points = ৳50 off) and referral codes (both people get a ৳100 coupon)
- In-app notifications (bell icon) for order updates, answers, price drops and rewards
- Newsletter sign-up with one-click unsubscribe

**Layout & UX**
- Every page (including 404/500) shares a top bar (search, cart, account) and a sidebar
  (shop links, categories, account). On phones the sidebar becomes a slide-out menu.
- Admin-managed hero banner slider, dark mode (remembered per device), Bangla digits mode (১২৩),
  taka in lakh format (৳12,50,000), scroll animations, empty-state illustrations, back-to-top button,
  floating WhatsApp/Messenger chat buttons
- Installable PWA: app icon, splash colours, offline page
- Accessibility: skip link, labelled buttons, keyboard-friendly search and option pickers, reduced-motion support

**Store management**
- Django admin (at `/manage-scb/`, configurable) for products (with gallery and variants), orders, banners,
  flash sales, bundles, delivery zones, questions, returns, coupons, subscribers and loyalty points
- Change history for products, variants, orders, coupons and returns (who changed what, django-simple-history)
- Sales dashboard (`/dashboard/`) and CSV sales reports (dashboard button and admin action)

**Security**
- Login lockout after 5 failed attempts for 30 minutes (django-axes), plus allauth's own throttle
- Honeypot fields against bots on sign-up and newsletter forms; rate limits on order tracking and questions
- Admin URL moved off `/admin/`; HTTPS, HSTS and secure cookies when `DEBUG=False`; no secrets in the code

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
| Database | PostgreSQL via `DATABASE_URL` (SQLite works too for quick tries) |
| Frontend | Django templates, Bootstrap 5.3, Bootstrap Icons, vanilla JS (fetch), AOS |
| Production | gunicorn, WhiteNoise (static files), django-storages (S3/R2 for uploads) |
| Charts | Chart.js |
| Payments | SSLCommerz v4 API |
| ML | scikit-learn (TF-IDF + cosine similarity) |
| Tests | Django test framework (119 tests) |

## Getting started

```bash
git clone <repo-url> && cd SmartcardBD
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

createdb smartcart_db         # PostgreSQL (Postgres.app or Homebrew)
cp .env.example .env          # set SECRET_KEY, and DATABASE_URL=postgresql://<you>@localhost:5432/smartcart_db
                              # with DATABASE_SSL_REQUIRE=False for a local database
python manage.py migrate
python manage.py seed_demo    # 17 products with photos and variants, banners, a flash sale, bundles, WELCOME10
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000. The admin is at `/manage-scb/` (set `ADMIN_URL` to change it) and the sales dashboard at `/dashboard/`.

Without `EMAIL_HOST`, emails (order confirmations, password resets) are printed to the terminal.

### With Docker

Needs only Docker; PostgreSQL runs in its own container.

```bash
docker compose up --build                          # Django on http://localhost:8000 + PostgreSQL
docker compose exec web python manage.py seed_demo
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py test
docker compose down                                # stop (add -v to also delete the database)
```

The project folder is mounted into the container, so code changes reload the dev server.
A `.env` file is optional here; compose sets `DEBUG` and the database URL itself.

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

### Scheduled jobs (cron)

```bash
python manage.py release_unpaid_orders        # every 15 min: free stock held by unpaid online orders
python manage.py send_price_alerts            # every 15 min: price-drop alerts (catches scheduled flash sales)
python manage.py send_abandoned_cart_emails   # hourly: remind logged-in customers about carts left 24h+
```

### Demo images

The demo photos in `products/demo_media/` come from Wikimedia Commons under free licences;
see `products/demo_media/CREDITS.md` or the **Image credits** page linked in the footer.

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

Or deploy the Docker image instead (Render, Railway, Fly.io or any VPS). The `Dockerfile` builds a
production image: dependencies, hashed static files, a non-root user, and gunicorn on `$PORT`.
Migrations run when the container starts. Pass the same environment variables to the container.

Static files (CSS/JS) are served by WhiteNoise, so no separate web server is needed.
HTTPS redirect and HSTS are on by default when `DEBUG=False`; `SECURE_HSTS_SECONDS` starts at
one hour, raise it to `31536000` once HTTPS works on your domain.

**Product images.** Hosts such as Render and Railway erase the local disk on every deploy, so
uploaded images would disappear. Create an S3-compatible bucket (Cloudflare R2 has a free tier)
and set `AWS_STORAGE_BUCKET_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
`AWS_S3_ENDPOINT_URL` and `AWS_S3_CUSTOM_DOMAIN` (see `.env.example`). On a VPS with a
persistent disk you can leave these empty and let nginx serve `media/`.
