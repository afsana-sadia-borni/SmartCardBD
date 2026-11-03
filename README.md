# SmartCart BD

A full-featured e-commerce web app for the Bangladeshi market, built with Django.
Customers can browse and search products, check out as a guest or with an account, pay
cash on delivery or online through SSLCommerz (bKash, Nagad, cards), and track their orders.
Staff run the shop from a mobile-friendly **store panel** (`/store/`), and a documented REST API
(JWT auth, Swagger docs) lets a mobile app use the same shop.

**Try it:** run `seed_demo` and log in with the demo shopper account `demo@smartcartbd.com` /
`SmartCart-Demo-2026` (the login page has a one-click button for it).

## Features

**Shopping**
- Product catalogue with categories, brands, sale prices and stock levels
- Product variants (size, colour, storage) with their own price, stock and SKU; picking a colour shows its photo
- Image gallery with hover zoom, quick-view popup, live search suggestions (debounced, keyboard friendly)
- Slide-out mini cart (AJAX add to cart), infinite scroll with skeleton loading, compare up to 4 products
- Flash sales with a live countdown (prices return to normal automatically), bundle offers, real "sold" counts
- Product Q&A (staff answer from the admin), review photos, "notify me if the price drops" alerts
- Search, filters (category, price range, brand, in stock) and sorting, with pagination; price sorting and
  filters use the price the customer pays now, flash sales included (computed in the database)
- SEO-friendly slug URLs (`/product/samsung-galaxy-a15/`); old `/product/<id>/` links redirect permanently
- AJAX cart: add, change quantity, remove, no page reloads; quantities are capped at available stock
- Coupons: percentage or flat, with minimum order, maximum discount, validity window and usage limit
- Recommendations: "You may also like" (TF-IDF content similarity) and "Frequently bought together" (order co-occurrence)

**Checkout & orders**
- Guest checkout, or logged-in checkout with saved addresses
- Bangladesh-specific: Division → District → Upazila/Thana dropdowns (all 64 districts, Dhaka city thanas), phone validation (`01XXXXXXXXX`), delivery charge and delivery time per zone (editable in the admin), free delivery over a threshold
- Order tracking without an account (`/track/`: order number + phone), gift wrap, order notes
- Return / refund requests within 7 days of delivery (with a photo); staff approve or reject in the admin
- Cash on Delivery, or pay online with bKash, Nagad, Rocket, card or internet banking (SSLCommerz opens straight
  on the chosen method; server-side validation and IPN)
- Order confirmation (with a PDF invoice attached) and status-update emails; invoice download on the order page
- Order tracking timeline, order history, customer cancellation (restocks items)
- Abandoned online payments are cancelled after `UNPAID_ORDER_TIMEOUT_MINUTES` (default 60) so their stock goes back on sale; a payment that arrives late revives the order if stock is still available, otherwise it is flagged for refund

**Accounts**
- Sign up with name, mobile number and email; log in with **email or mobile number** (01XXXXXXXXX);
  password reset, show/hide password, optional Google login (django-allauth)
- Address book with a default address
- Wishlist
- Verified-purchase reviews and ratings (only for delivered orders)
- Reward points (1 point per ৳100, 100 points = ৳50 off) and referral codes (both people get a ৳100 coupon)
- In-app notifications (bell icon) for order updates, answers, price drops and rewards, plus optional
  web push notifications to the phone or desktop (works with the site closed)
- Abandoned-cart reminder emails, for logged-in customers and for guests who typed their email at checkout
- Newsletter sign-up with one-click unsubscribe

**Layout & UX**
- Every page (including 404/500) shares a top bar (search, cart, account) and a sidebar
  (shop links, categories, account). On phones the sidebar becomes a slide-out menu.
- Admin-managed hero banner slider, dark mode (remembered per device), Bangla digits mode (১২৩),
  taka in lakh format (৳12,50,000), scroll animations, empty-state illustrations, back-to-top button,
  floating WhatsApp/Messenger chat buttons
- Installable PWA: app icon, splash colours, offline page, push notifications
- Uploaded images get 400/800/1600px WebP copies automatically (about 90% smaller on phones)
- About, delivery, return & refund, privacy and terms pages (delivery charges come from the admin's zones)
- Accessibility: skip link, labelled buttons, keyboard-friendly search and option pickers, reduced-motion support

**Store panel** (`/store/`, for the owner and staff)
- Staff log in on the normal login page and land in the panel; a "Store" button in the shop's top bar leads back.
  Visitors and customers get a plain 404 at `/store/`, so the panel isn't advertised
- Dashboard: today's sales, a to-do list (new orders, orders to ship, returns, questions, low stock), sales charts
- Orders: status tabs and search; one-click Confirm → Mark shipped → Mark delivered (COD marked paid on delivery),
  cancel with restock, call/WhatsApp the customer, print the invoice, full status history with who did what
- Products: search and filters, quick stock and visibility changes from the list, add/edit with options
  (size/colour/storage, each with its own stock and price) and photo gallery
- Flash sales, coupons, home banners, delivery charges, return decisions, answering customer questions, customers
- Team and roles: the owner adds staff by email as *Order manager* or *Catalog manager*; each sees only their sections
- Dark mode, phone-friendly layout; Django admin (`/manage-scb/`) stays as "Advanced settings" for the owner
- Change history for products, variants, orders, coupons and returns (django-simple-history), CSV sales reports

**REST API** (`/api/`, docs at `/api/docs/`)
- Products (search, filters, sorting, pagination), product detail with variants and reviews, categories
- JWT login with email and password, profile with reward points, your orders, and placing Cash on Delivery
  orders with the same stock locking, prices, coupons and address validation as the website
- Rate limits on login and ordering; OpenAPI schema generated by drf-spectacular

**Security**
- Login lockout after 5 failed attempts for 30 minutes (django-axes), plus allauth's own throttle
- Honeypot fields against bots on sign-up and newsletter forms; rate limits on order tracking and questions
- Admin URL moved off `/admin/`; HTTPS, HSTS and secure cookies when `DEBUG=False`; no secrets in the code

## Engineering notes

- **No overselling.** `orders/services.py::create_order` locks the product rows with `SELECT ... FOR UPDATE` inside a transaction, re-checks stock, and decrements it with `F()` expressions. If two customers try to buy the last unit at the same moment, only one order succeeds.
- **Prices are never trusted from the client or session.** The cart stores only product ids and quantities. Prices are read from the database at checkout, and each `OrderItem` keeps a snapshot of the title and price paid.
- **Payments are verified server to server.** A success redirect from the gateway is not enough on its own. Every payment is re-validated with the SSLCommerz validation API (status, transaction id, amount and currency must match), and `mark_order_paid` is idempotent, so the success callback and the IPN can both arrive safely.
- **Business logic lives in services**, not views (`orders/services.py`, `orders/payments.py`, `recommendations/engine.py`), which keeps views thin and the logic testable.
- **Slow work runs in the background.** Emails (with the PDF invoice), push notifications and WebP image copies are Celery tasks queued with `transaction.on_commit`, so a request never waits for SMTP and a task never sees an order that was rolled back. Without Redis the tasks simply run inline.
- **One set of rules for the website and the API.** The API reuses the checkout form's validation, `create_order` and the product filters (`products/filters.py`) instead of re-implementing them.
- **Configuration is read from the environment** (`.env`). No secrets are kept in the code.

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, Django 6.1 |
| Auth | django-allauth, Simple JWT (API) |
| API | Django REST Framework, drf-spectacular (OpenAPI / Swagger) |
| Background jobs | Celery + Redis (worker and beat scheduler) |
| Database | PostgreSQL via `DATABASE_URL` (SQLite works too for quick tries) |
| Frontend | Django templates, Bootstrap 5.3, Bootstrap Icons, vanilla JS (fetch), AOS |
| Production | Docker, gunicorn, WhiteNoise (static files), django-storages (S3/R2 for uploads) |
| Charts | Chart.js |
| Payments | SSLCommerz v4 API |
| PDF / push | ReportLab (invoices), pywebpush (Web Push / VAPID) |
| ML | scikit-learn (TF-IDF + cosine similarity) |
| Tests | Django test framework (168 tests) |

## Getting started

```bash
git clone <repo-url> && cd SmartcardBD
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

createdb smartcart_db         # PostgreSQL (Postgres.app or Homebrew)
cp .env.example .env          # set SECRET_KEY, and DATABASE_URL=postgresql://<you>@localhost:5432/smartcart_db
                              # with DATABASE_SSL_REQUIRE=False for a local database
python manage.py migrate
python manage.py seed_demo    # 17 products with photos and variants, banners, a flash sale, bundles, WELCOME10,
                              # and the demo shopper account
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000 and log in with the superuser: staff land in the store panel (`/store/`).
The Django admin is at `/manage-scb/` (set `ADMIN_URL` to change it; `/admin/` redirects there while `DEBUG` is on).

Without `EMAIL_HOST`, emails (order confirmations, password resets) are printed to the terminal.

### With Docker

Needs only Docker; PostgreSQL runs in its own container.

```bash
docker compose up --build                          # http://localhost:8000: Django, PostgreSQL, Redis, Celery
docker compose exec web python manage.py seed_demo
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py test
docker compose down                                # stop (add -v to also delete the database)
```

Five containers start: `web` (Django dev server), `db` (PostgreSQL), `redis`, `worker` (Celery: emails,
push notifications, WebP images) and `beat` (scheduled jobs). The project folder is mounted into the
containers, so code changes reload the dev server; restart the worker after changing a task
(`docker compose restart worker`).
A `.env` file is optional here; compose sets `DEBUG` and the database URL itself.

### Online payments (optional)

1. Create a free sandbox store at https://developer.sslcommerz.com/registration/
2. Put the store ID and password from SSLCommerz's email in `.env` (`SSLCOMMERZ_STORE_ID`, `SSLCOMMERZ_STORE_PASSWORD`,
   keep `SSLCOMMERZ_SANDBOX=True` for testing) and restart the server.
3. Checkout then offers bKash, Nagad, Rocket, card, internet banking and "other online methods" next to Cash on
   Delivery. The SSLCommerz page opens on the method the customer picked (Nagad opens the mobile-banking list).
4. For real money, ask SSLCommerz for a live store, then set the live ID/password and `SSLCOMMERZ_SANDBOX=False`.

The IPN callback must be reachable from the internet. Locally, the success redirect still validates and confirms the payment.

Unpaid online orders are released automatically whenever someone checks out. In production you can also
run `python manage.py release_unpaid_orders` from a cron job (for example every 15 minutes).

### Google login (optional)

Create an OAuth client in Google Cloud Console with the redirect URI
`http://localhost:8000/accounts/google/login/callback/`, then set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.

### Background and scheduled jobs (Celery + Redis)

Set `REDIS_URL` (for example `redis://localhost:6379/0`) and run a worker and the scheduler next to the web server:

```bash
celery -A config worker --loglevel=info   # emails, push notifications, WebP image copies
celery -A config beat --loglevel=info     # runs the jobs below on schedule (CELERY_BEAT_SCHEDULE)
```

| Job | Schedule |
|---|---|
| Release stock held by unpaid online orders | every 10 min |
| Price-drop alerts (catches flash sales that start on schedule) | every 15 min |
| Abandoned-cart reminders (carts untouched for 24h) | hourly |

Without `REDIS_URL`, tasks run inline in the web process and everything still works; then run the
scheduled jobs from cron instead:

```bash
python manage.py release_unpaid_orders
python manage.py send_price_alerts
python manage.py send_abandoned_cart_emails
python manage.py make_webp_images     # one-off: WebP copies for images uploaded before this feature
```

### Push notifications (optional)

```bash
python manage.py generate_vapid_keys   # prints VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY; put them in .env
```

Customers then see a "Turn on" button on their notifications page. Browsers only allow push on
`https://` sites (and on `localhost`).

### Store details

Set `SUPPORT_EMAIL`, `SUPPORT_PHONE`, `BUSINESS_ADDRESS` and `TRADE_LICENSE` to show them on the About
and Privacy pages. Set `SITE_URL` to the public address, for links in emails.

## REST API

Interactive docs: http://localhost:8000/api/docs/ (OpenAPI schema at `/api/schema/`).

```bash
# Browse (no login needed)
curl "http://localhost:8000/api/products/?q=samsung&sort=price_asc"
curl http://localhost:8000/api/products/samsung-galaxy-a15/

# Log in, then send the access token
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/token/ \
  -d email=demo@smartcartbd.com -d password=SmartCart-Demo-2026 | python -c "import sys,json;print(json.load(sys.stdin)['access'])")
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/me/
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/orders/

# Place a Cash on Delivery order
curl -X POST http://localhost:8000/api/orders/ -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"items": [{"product_id": 1, "quantity": 1}], "full_name": "Demo Customer", "phone": "01712345678",
       "district": "Dhaka", "upazila": "Mirpur (Dhaka City)", "area": "Mirpur 10", "address_line": "House 12"}'
```

| Endpoint | Method | Auth | |
|---|---|---|---|
| `/api/auth/token/`, `/api/auth/token/refresh/` | POST | - | JWT access (30 min) and refresh (7 days) tokens |
| `/api/categories/` | GET | - | All categories |
| `/api/products/` | GET | - | `q`, `category`, `brand`, `min_price`, `max_price`, `in_stock`, `sort`, `page` |
| `/api/products/<slug>/` | GET | - | Gallery, variants, latest reviews |
| `/api/me/` | GET | JWT | Profile, reward points, referral link |
| `/api/orders/` | GET, POST | JWT | Your orders; place a COD order |
| `/api/orders/<order_number>/` | GET | JWT | One order, with its invoice link |

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
addresses, wishlist, reviews, search and filters (including flash-sale prices), recommendations,
the REST API (auth, orders, permissions), PDF invoices, push notifications, abandoned-cart emails,
WebP images, the demo account, policy pages, the shared layout and error pages, and production
settings (`check --deploy`).

## Project structure

```
accounts/         Address book, wishlist, loyalty points, notifications, web push, BD geo data
api/              REST API: serializers, views, JWT login, OpenAPI docs
cart/             Session cart (cart.py), AJAX cart and coupon views, abandoned-cart reminders
core/             PWA (manifest, service worker), policy pages, middleware, rate limiting, email task
orders/           Order & Coupon models, checkout, services (stock locking), PDF invoice,
                  SSLCommerz integration, admin, CSV reports, emails, Celery tasks
products/         Catalogue, filters, reviews, flash sales, WebP images, seed_demo command, template tags
recommendations/  TF-IDF similar products, frequently-bought-together
store/            Store panel for the owner and staff: orders, catalog, promotions, returns, team & roles
templates/        Base layout, shared partials, django-allauth overrides
static/           CSS, JS, images
config/           Settings, root URLs, Celery app, layout/error-page/settings tests
docker/           Container entrypoint (runs migrations)
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
