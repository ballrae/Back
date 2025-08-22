import os
import django
import requests
import json
from django.db import transaction

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ballrae_backend.settings")
django.setup()

from ballrae_backend.games.models import Player
from ballrae_backend.players.models import Batter, Pitcher

players = Player.objects.all()

headers = {
    "User-Agent": "Mozilla/5.0"
}

for p in players:
    pcode = p.pcode
    position = p.position
    player = Player.objects.get(pcode=pcode)

    url = f"https://m.sports.naver.com/ajax/player/record?category=kbo&playerId={pcode}"
    try:
        res = requests.get(url, headers=headers)
        data = res.json()

        if 'playerEndRecord' not in data or not data['playerEndRecord']:
            print(f"[{pcode}] No record data.")
            continue

        record_data = json.loads(data['playerEndRecord']['record'])
        season_data = record_data['season'][1]  # 최신 시즌 기준 (index 1)

        if position == 'P':
            era = season_data.get('era')
            w = season_data.get('w')
            l = season_data.get('l')
            sv = season_data.get('sv')
            war = season_data.get('war')

            Pitcher.objects.update_or_create(
                player=player,
                season='2025',
                defaults={
                    'era': era,
                    'w': w,
                    'l': l,
                    'sv': sv,
                    'war': war
                }
            )
            print(f"[{pcode}] Pitcher updated")

        elif position == 'B':
            babip = season_data.get('babip')
            war = season_data.get('war')
            wrc = season_data.get('wrcPlus')

            Batter.objects.update_or_create(
                player=player,
                season='2025',                
                defaults={
                    'babip': babip,
                    'war': war,
                    'wrc': wrc
                }
            )
            print(f"[{pcode}] Batter updated")
    
    except IndexError:
        print(f'[{pcode}] 1군 기록 없음')
        continue

    except Exception as e:
        print(f"[{pcode}] Error: {e}")