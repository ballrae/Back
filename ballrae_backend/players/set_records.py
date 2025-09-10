import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ballrae_backend.settings")
django.setup()

from ballrae_backend.games.models import AtBat, Player
from ballrae_backend.players.models import Batter, Pitcher
from django.db import transaction
from ballrae_backend.players.services import update_recent_5_stats_from_atbats, update_players_war_and_stats
from ballrae_backend.players.services import save_batter_transactionally, save_pitcher_transactionally, save_batter_career, save_pitcher_career
from ballrae_backend.games.services import update_team_wins_loses_and_streak

players = Player.objects.all()
for player in players:
    if player.position == 'B':
        save_batter_transactionally(player)
        save_batter_career(player)
        update_recent_5_stats_from_atbats(player)
    elif player.position == 'P':
        save_pitcher_transactionally(player)    
        save_pitcher_career(player)
    else: print(player.player_name, "포지션 정보 없음")

    update_players_war_and_stats(player)
    update_team_wins_loses_and_streak()
