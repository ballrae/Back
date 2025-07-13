import os
from celery import Celery
from dotenv import load_dotenv

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ballrae_backend.settings")

app = Celery("ballrae_backend")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
app.conf.task_default_queue = 'default'