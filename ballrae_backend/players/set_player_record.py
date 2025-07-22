import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ballrae_backend.settings")
django.setup()

from ballrae_backend.games.models import AtBat, Player
from ballrae_backend.players.models import Batter, Pitcher
from django.db import transaction
from ballrae_backend.players.services import save_batter_transactionally, save_pitcher_transactionally

players = Player.objects.all()
for player in players:
    if player.position == 'B':
        save_batter_transactionally(player)
    elif player.position == 'P':
        save_pitcher_transactionally(player)
    else: print(player.player_name, "포지션 정보 없음")