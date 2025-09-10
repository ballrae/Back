# games/tasks.py
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ballrae_backend.settings")
django.setup()

from ballrae_backend.streaming.producer import get_game_datas
from datetime import datetime, timedelta
from celery import shared_task

@shared_task
def save_todays_games():
    today = datetime.today()
    yesterday = today - timedelta(days=1)
    yesterday = yesterday.strftime('%Y%m%d')
    # print(yesterday)
    get_game_datas(yesterday, yesterday)
