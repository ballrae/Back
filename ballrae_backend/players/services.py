# players/services.py
from django.db import transaction
from ballrae_backend.games.models import AtBat, Inning, Game, Player
from .models import Pitcher, Batter
import json
from django.db.models import Q
import requests

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
        actual_player=player.pcode,
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
        season=2025,
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
        # pitcher=player.id,
        pitcher=player.pcode,
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
        season=2025,
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

@transaction.atomic
def save_batter_career(player: Player):
    atbats = AtBat.objects.filter(actual_player=player.pcode)  # 전체

    total_games = atbats.values("inning__game_id").distinct().count()
    pa = atbats.count()
    ab = atbats.exclude(main_result__iregex="볼넷|사구|4구|몸에|희생플라이|희생번트").count()
    walks = atbats.filter(main_result__iregex="볼넷|사구|4구|몸에").count()
    strikeouts = atbats.filter(main_result__iregex="삼진|낫 아웃").count()
    home_runs = atbats.filter(main_result__icontains="홈런").count()
    singles = atbats.filter(main_result__iregex="1루타|안타").count()
    doubles = atbats.filter(main_result__icontains="2루타").count()
    triples = atbats.filter(main_result__icontains="3루타").count()

    Batter.objects.update_or_create(
        player=player,
        season=None,  # 통산
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
def save_pitcher_career(player: Player):
    atbats = AtBat.objects.filter(
        pitcher=player.pcode  # 전체 경기 대상
    )

    total_games = atbats.values("inning__game_id").distinct().count()
    pa = atbats.count()
    ab = atbats.exclude(main_result__iregex=r'볼넷|사구|4구|몸에|희생플라이|희생번트').count()
    walks = atbats.filter(main_result__iregex=r'볼넷|사구|4구|몸에').count()
    strikeouts = atbats.filter(main_result__iregex=r'삼진|낫 아웃').count()
    homeruns = atbats.filter(main_result__icontains='홈런').count()
    singles = atbats.filter(main_result__iregex=r'1루타|안타').count()
    doubles = atbats.filter(main_result__icontains='2루타').count()
    triples = atbats.filter(main_result__icontains='3루타').count()

    innings = calculate_innings(atbats)

    Pitcher.objects.update_or_create(
        player=player,
        season=None,  # 통산 기록은 season 없이 저장
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

def get_realtime_batter(pcode):
    url = f"https://m.sports.naver.com/ajax/player/record?category=kbo&playerId={pcode}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        # "Referer": "https://m.sports.naver.com/game/20250503OBSS02025/relay"
    }

    response = requests.get(url, headers=headers)
    data = response.json()

    direction = json.loads(data['playerEndRecord']['chart'])['direction'] 

    # DB에서 타자 기록 데이터 가져오기
    try:
        player = Player.objects.filter(pcode=pcode).first()
        
        if not player:
            season_stats = None
            career_stats = None
        else:
            # 2025 시즌 기록
            season_2025 = None
            try:
                season_2025 = Batter.objects.get(player=player, season=2025)
            except Batter.DoesNotExist:
                pass
            
            # 통산 기록
            career = None
            try:
                career = Batter.objects.get(player=player, season=None)
            except Batter.DoesNotExist:
                pass
            
            # 기록 데이터 계산
            def calculate_stats(batter_obj):
                if not batter_obj:
                    return None
                
                ab = batter_obj.ab or 0
                pa = batter_obj.pa or 0
                hits = (batter_obj.singles or 0) + (batter_obj.doubles or 0) + (batter_obj.triples or 0) + (batter_obj.homeruns or 0)
                
                # 타율 계산
                avg = round(hits / ab, 3) if ab else 0.0
                
                # 출루율 계산
                obp = round((hits + (batter_obj.walks or 0)) / pa, 3) if pa else 0.0
                
                return {
                    "ab": ab,
                    "hits": hits,
                    "homeruns": batter_obj.homeruns or 0,
                    "rbi": 0,  # 타점 필드가 없으므로 0으로 설정
                    "obp": obp,
                    "avg": avg
                }
            
            season_stats = calculate_stats(season_2025)
            career_stats = calculate_stats(career)
        
    except Exception as e:
        season_stats = None
        career_stats = None

    result = {
        "batter": direction,
        "season_2025": season_stats,
        "career": career_stats
    }

    return result

def get_realtime_pitcher(pcode):
    url = f"https://m.sports.naver.com/ajax/player/record?category=kbo&playerId={pcode}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        # "Referer": "https://m.sports.naver.com/game/20250503OBSS02025/relay"
    }

    response = requests.get(url, headers=headers)
    data = response.json()

    data = json.loads(data['playerEndRecord']['chart'])['pit_kind']['player']

    valid_pitches = [v for v in data.values() if v['pit_rt'] is not None]
    sorted_pitches = sorted(valid_pitches, key=lambda x: x['pit_rt'], reverse=True)
    top_3 = sorted_pitches[:3]

    # DB에서 투수 기록 데이터 가져오기
    try:
        player = Player.objects.filter(pcode=pcode).first()
        
        if not player:
            season_stats = None
            career_stats = None
        else:
            # 2025 시즌 기록
            season_2025 = None
            try:
                season_2025 = Pitcher.objects.get(player=player, season=2025)
            except Pitcher.DoesNotExist:
                pass
            
            # 통산 기록
            career = None
            try:
                career = Pitcher.objects.get(player=player, season=None)
            except Pitcher.DoesNotExist:
                pass
            
            # 기록 데이터 계산
            def calculate_stats(pitcher_obj):
                if not pitcher_obj:
                    return None
                
                inn = pitcher_obj.innings or 0
                k = pitcher_obj.strikeouts or 0
                bb = pitcher_obj.walks or 0
                hits = (pitcher_obj.singles or 0) + (pitcher_obj.doubles or 0) + (pitcher_obj.triples or 0) + (pitcher_obj.homeruns or 0)
                
                # ERA 계산 (타점이 없으므로 0으로 설정)
                era = 0.0
                
                # K/9 계산
                k9 = round(k * 9.0 / inn, 2) if inn else 0.0
                
                # BB/9 계산
                bb9 = round(bb * 9.0 / inn, 2) if inn else 0.0
                
                # WHIP 계산
                whip = round((bb + hits) / inn, 2) if inn else 0.0
                
                return {
                    "innings": inn,
                    "strikeouts": k,
                    "walks": bb,
                    "hits": hits,
                    "era": era,
                    "k9": k9,
                    "bb9": bb9,
                    "whip": whip
                }
            
            season_stats = calculate_stats(season_2025)
            career_stats = calculate_stats(career)
        
    except Exception as e:
        season_stats = None
        career_stats = None

    result = {
        "pitcher": [
            {"type": p['pit'], "rate": p['pit_rt'], "speed": p['speed']}
            for p in top_3
        ],
        "season_2025": season_stats,
        "career": career_stats
    }

    return result