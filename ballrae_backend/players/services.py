# players/services.py
from django.db import transaction
from ballrae_backend.games.models import AtBat, Inning, Game, Player
from .models import Pitcher, Batter
import json
from django.db.models import Q

cutoff_date = "20250322"

def calculate_innings(atbats):
    innings_outs = 0
    previous_out = None
    previous_game = None

    for ab in atbats.order_by("inning__game_id", "id"):
        current_game = ab.inning.game_id
        current_out = int(ab.out or 0)

        if previous_out is None or previous_game != current_game:
            innings_outs += current_out
        elif current_out >= previous_out:
            innings_outs += current_out - previous_out
        else:
            innings_outs += current_out  # 새로운 이닝에서 초기화된 경우

        previous_out = current_out
        previous_game = current_game

    # 아웃카운트 → 이닝 포맷
    whole = innings_outs // 3
    remainder = innings_outs % 3
    decimal = 0.1 if remainder == 1 else 0.2 if remainder == 2 else 0.0
    return round(whole + decimal, 1)

@transaction.atomic
def save_batter_transactionally(player: Player):
    atbats = AtBat.objects.filter(
        actual_player=player.id,
        inning__game_id__gte=cutoff_date
    )

    # 기본 통계 초기화
    total_games = atbats.values("inning__game_id").distinct().count()
    pa = atbats.count()

    ab = atbats.exclude(main_result__iregex="볼넷|사구|4구|몸에|희생플라이|희생번트").count()
    walks = atbats.filter(main_result__iregex="볼넷|사구|4구|몸에").count()
    strikeouts = atbats.filter(main_result__iregex="삼진|낫 아웃").count()
    home_runs = atbats.filter(main_result__icontains="홈런").count()
    singles = atbats.filter(main_result__iregex="1루타|안타").count()
    doubles = atbats.filter(main_result__icontains="2루타").count()
    triples = atbats.filter(main_result__icontains="3루타").count()

    # 기존 기록 있으면 업데이트, 없으면 생성
    batter, _ = Batter.objects.update_or_create(
        player=player,
        defaults={
            "games": total_games,
            "pa": pa,
            "ab": ab,
            "walks": walks,
            "strikeouts": strikeouts,
            "homeruns": home_runs,
            "singles": singles,
            "doubles": doubles,
            "triples": triples,
        }
    )

@transaction.atomic
def save_pitcher_transactionally(player: Player):
    atbats = AtBat.objects.filter(
        pitcher=player.id,
        inning__game_id__gte=cutoff_date
    )

    # 기본 통계 계산
    total_games = atbats.values("inning__game_id").distinct().count()
    pa = atbats.count()
    ab = atbats.exclude(main_result__iregex="볼넷|사구|4구|몸에|희생플라이|희생번트").count()
    walks = atbats.filter(main_result__iregex=r'볼넷|사구|4구|몸에').count()
    strikeouts = atbats.filter(main_result__iregex=r'삼진|낫 아웃').count()
    homeruns = atbats.filter(main_result__icontains='홈런').count()
    singles = atbats.filter(main_result__iregex=r'1루타|안타').count()
    doubles = atbats.filter(main_result__icontains='2루타').count()
    triples = atbats.filter(main_result__icontains='3루타').count()

    innings = calculate_innings(atbats)

    # 기존 기록 있으면 업데이트, 없으면 생성
    pitcher, _ = Pitcher.objects.update_or_create(
        player=player,
        defaults={
            "games": total_games,
            "pa": pa,
            "ab": ab,
            "walks": walks,
            "strikeouts": strikeouts,
            "homeruns": homeruns,
            "singles": singles,
            "doubles": doubles,
            "triples": triples,
            "innings": innings,
        }
    )