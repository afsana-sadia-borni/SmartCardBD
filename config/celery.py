"""Celery app: background jobs (emails, push notifications) and scheduled jobs (celery beat).

Without CELERY_BROKER_URL / REDIS_URL, tasks run inline in the web process, so the site
works the same without Redis; only the scheduled jobs then need cron (see README).
"""
import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('smartcart')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
