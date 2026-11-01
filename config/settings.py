"""
Django settings for SmartCart BD.

All secrets and environment-specific values are read from environment
variables (loaded from `.env` in development). See `.env.example`.
"""

import os
import sys
import warnings
from pathlib import Path

import dj_database_url
from django.core.management.utils import get_random_secret_key
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


def env_list(name, default=''):
    return [item.strip() for item in os.getenv(name, default).split(',') if item.strip()]


DEBUG = env_bool('DEBUG', False)

SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError('SECRET_KEY environment variable is required when DEBUG is off.')
    # No key in the code: generate a throwaway one for local development.
    # Logins reset on every restart until SECRET_KEY is set in .env.
    SECRET_KEY = get_random_secret_key()

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', 'localhost,127.0.0.1')
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django.contrib.humanize',

    'allauth',
    'allauth.account',
    'allauth.socialaccount',

    'accounts',
    'products',
    'cart',
    'orders',
    'recommendations',
]

GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    INSTALLED_APPS.append('allauth.socialaccount.providers.google')
    SOCIALACCOUNT_PROVIDERS = {
        'google': {
            'APPS': [{'client_id': GOOGLE_CLIENT_ID, 'secret': GOOGLE_CLIENT_SECRET, 'key': ''}],
            'SCOPE': ['profile', 'email'],
        }
    }

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'cart.context_processors.cart',
                'products.context_processors.categories',
                'accounts.context_processors.wishlist',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# Uses DATABASE_URL (e.g. Neon Postgres) when set, otherwise a local SQLite file.

DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL:
    # SSL only applies to Postgres; SQLite rejects the sslmode option.
    is_postgres = DATABASE_URL.startswith(('postgres://', 'postgresql://'))
    DATABASES = {
        'default': dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            ssl_require=is_postgres and env_bool('DATABASE_SSL_REQUIRE', True),
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

if 'test' in sys.argv:
    # Real hashers are deliberately slow; tests don't need that.
    PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]


# Internationalization

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Dhaka'
USE_I18N = True
USE_TZ = True


# Static & media files

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# WhiteNoise serves static files in production. The hashed (manifest) storage needs
# `collectstatic`, so it is only used when DEBUG is off and tests aren't running.
USE_MANIFEST_STATIC = not DEBUG and 'test' not in sys.argv
if not USE_MANIFEST_STATIC:
    # Without collectstatic there is no STATIC_ROOT yet; let WhiteNoise use the
    # app/static directories directly instead of warning about it.
    WHITENOISE_USE_FINDERS = True
    warnings.filterwarnings('ignore', message='No directory at', module='whitenoise.base')
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        'BACKEND': (
            'whitenoise.storage.CompressedManifestStaticFilesStorage'
            if USE_MANIFEST_STATIC
            else 'django.contrib.staticfiles.storage.StaticFilesStorage'
        ),
    },
}

# Uploaded product images. Hosts like Render/Railway wipe the local disk on every
# deploy, so in production set these to use S3-compatible storage
# (Cloudflare R2, AWS S3, Backblaze B2, ...).
AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME')
if AWS_STORAGE_BUCKET_NAME:
    STORAGES['default'] = {'BACKEND': 'storages.backends.s3.S3Storage'}
    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
    AWS_S3_ENDPOINT_URL = os.getenv('AWS_S3_ENDPOINT_URL') or None
    AWS_S3_REGION_NAME = os.getenv('AWS_S3_REGION_NAME') or None
    AWS_S3_CUSTOM_DOMAIN = os.getenv('AWS_S3_CUSTOM_DOMAIN') or None
    AWS_QUERYSTRING_AUTH = env_bool('AWS_QUERYSTRING_AUTH', False)
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

SITE_ID = 1
SITE_NAME = 'SmartCart BD'


# Auth (django-allauth)

LOGIN_URL = 'account_login'
LOGIN_REDIRECT_URL = 'home'
ACCOUNT_LOGOUT_REDIRECT_URL = 'home'
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = os.getenv('ACCOUNT_EMAIL_VERIFICATION', 'optional')
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_SESSION_REMEMBER = None
SOCIALACCOUNT_LOGIN_ON_GET = False


# Email
# Without EMAIL_HOST, emails are printed to the console.

EMAIL_HOST = os.getenv('EMAIL_HOST')
if EMAIL_HOST:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
    EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
    EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', True)
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'SmartCart BD <noreply@smartcartbd.local>')


# Shop settings (BDT)

SHIPPING_INSIDE_DHAKA = int(os.getenv('SHIPPING_INSIDE_DHAKA', 60))
SHIPPING_OUTSIDE_DHAKA = int(os.getenv('SHIPPING_OUTSIDE_DHAKA', 120))
FREE_SHIPPING_MIN = int(os.getenv('FREE_SHIPPING_MIN', 2000))
LOW_STOCK_THRESHOLD = 5
# Unpaid online-payment orders are cancelled (and restocked) after this many minutes.
UNPAID_ORDER_TIMEOUT_MINUTES = int(os.getenv('UNPAID_ORDER_TIMEOUT_MINUTES', 60))


# SSLCommerz (free sandbox account: https://developer.sslcommerz.com/registration/)

SSLCOMMERZ_STORE_ID = os.getenv('SSLCOMMERZ_STORE_ID', '')
SSLCOMMERZ_STORE_PASSWORD = os.getenv('SSLCOMMERZ_STORE_PASSWORD', '')
SSLCOMMERZ_SANDBOX = env_bool('SSLCOMMERZ_SANDBOX', True)


# Production security

if not DEBUG:
    SESSION_COOKIE_SECURE = env_bool('SECURE_COOKIES', True)
    CSRF_COOKIE_SECURE = env_bool('SECURE_COOKIES', True)
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_CONTENT_TYPE_NOSNIFF = True
    # Test requests are plain HTTP, so don't redirect them to HTTPS.
    SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', True) and 'test' not in sys.argv
    # Browsers remember HSTS, so start short (1 hour) and raise it to e.g. 31536000
    # (1 year) once HTTPS works everywhere. Set to 0 to turn it off.
    SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', 3600))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', False)
    SECURE_HSTS_PRELOAD = env_bool('SECURE_HSTS_PRELOAD', False)
