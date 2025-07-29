import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ballrae_backend.settings")
django.setup()

from ballrae_backend.games.models import AtBat, Player
from ballrae_backend.players.models import Batter, Pitcher
from django.db import transaction
import requests

pitchers = Pitcher.objects.all()
batters = Batter.objects.all()
players = Player.objects.all()

for p in players:
    pcode = p.pcode
    type = p.position

    url = f"https://m.sports.naver.com/ajax/player/record?category=kbo&playerId={p.pcode}"

    headers = {"User-Agent": "Mozilla/5.0", "Referer": url}
    res = requests.get(url, headers=headers)
    data = res.json()
    
    if type == 'P':
        
    elif type == 'B':