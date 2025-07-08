# games/routing.py

from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/games/(?P<game_id>\w+)/$', consumers.RelayConsumer.as_asgi()),
]