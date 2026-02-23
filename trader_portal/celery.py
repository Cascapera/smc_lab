import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "trader_portal.settings.dev")

app = Celery("trader_portal")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
