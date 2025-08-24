# players/services.py
from django.db import transaction
from ballrae_backend.games.models import AtBat, Inning, Game, Player
from .models import Pitcher, Batter, BatterRecent
import json
from django.db.models import Q
import requests
from collections import defaultdict
from django.utils.timezone import now
from ballrae_backend.streaming.redis_client import redis_client
import datetime
import re

cutoff_date = "20250322"

def calculate_redis_innings(atbats: list, pcode: str) -> float:
    innings_outs = 0
    previous_out = None
    previous_game = None

    # 이 투수가 던진 타석만 추출
    filtered = [ab for ab in atbats if ab.get("pitcher") == pcode]
    # print(len(filtered))
    sorted_atbats = sorted(filtered, key=lambda ab: (
        ab.get("game_id"), ab.get("inning", 0), ab.get("order", 0))
    )

    for ab in sorted_atbats:
        current_game = ab.get("game_id")
        current_out = int(ab.get("out") or 0)

        if previous_out is None or previous_game != current_game:
            innings_outs += current_out
            print(innings_outs)
        elif current_out >= previous_out:
            innings_outs += current_out - previous_out
            print(innings_outs)            
        else:
            innings_outs += current_out  # 이닝이 바뀌었거나 리셋됐을 때
            print(innings_outs)

        previous_out = current_out
        previous_game = current_game

    # 이닝 포맷 변환
    whole = innings_outs // 3
    remainder = innings_outs % 3
    decimal = 0.1 if remainder == 1 else 0.2 if remainder == 2 else 0.0
    return round(whole + decimal, 1)


def get_today_stat_from_redis(player: Player) -> dict:
    today = datetime.date.today()
    prefix = f"game:{today.strftime('%Y%m%d')}"

    # today = "20250823"
    # prefix = f"game:{today}"

    keys = redis_client.keys(f"{prefix}*")
    keys = [k for k in keys if ":inning:" in k]

    total_stat = defaultdict(int)

    for key in keys:
        raw = redis_client.get(key)
        if not raw:
            continue

        atbats = json.loads(raw).get('atbats', [])
        if player.position == 'P':
            total_stat['innings'] = calculate_redis_innings(atbats, player.pcode)

        for ab in atbats:
            if not ab:
                continue

            is_batter = ab.get('actual_batter') == player.pcode
            is_pitcher = ab.get('pitcher') == player.pcode
            if not (is_batter or is_pitcher):
                continue

            main_result = ab.get("main_result", "")
            pitch_count = ab.get("pitch_num", [])
            # runs = int(ab.get("score", 0))
            runs = 0

            if player.position == 'B' and is_batter:
                total_stat['pa'] += 1

                if not any(x in main_result for x in ["볼넷", "사구", "4구", "몸에", "희생플라이", "희생번트"]):
                    total_stat['ab'] += 1
                if any(x in main_result for x in ["안타", "1루타", "2루타", "3루타", "홈런"]):
                    total_stat['hits'] += 1
                if "홈런" in main_result:
                    total_stat['homeruns'] += 1
                if any(x in main_result for x in ["볼넷", "사구", "4구", "몸에"]):
                    total_stat['bb'] += 1
                if any(x in main_result for x in ["삼진", "낫 아웃"]):
                    total_stat['strikeouts'] += 1

            elif player.position == 'P' and is_pitcher:
                if any(x in main_result for x in ["안타", "1루타", "2루타", "3루타", "홈런"]):
                    total_stat['hits'] += 1
                if ab.get('actual_batter') and any(x in main_result for x in ["삼진", "낫 아웃"]):
                    total_stat['strikeouts'] += 1
                total_stat['pitches'] += len(pitch_count or [])
                total_stat['runs'] += runs

        if player.position == 'B':
            return {
                "pa": total_stat.get("pa", 0),
                "ab": total_stat.get("ab", 0),
                "hits": total_stat.get("hits", 0),
                "homeruns": total_stat.get("homeruns", 0),
                "bb": total_stat.get("bb", 0),
                "strikeouts": total_stat.get("strikeouts", 0),
            }

        elif player.position == 'P':
            return {
                "pitches": total_stat.get("pitches", 0),
                "runs": total_stat.get("runs", 0),
                "innings": total_stat.get("innings", 0),
                "hits": total_stat.get("hits", 0),
                "strikeouts": total_stat.get("strikeouts", 0),
            }

def update_players_war_and_stats(p):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    pcode = p.pcode
    position = p.position
    player = Player.objects.get(pcode=pcode)

    url = f"https://m.sports.naver.com/ajax/player/record?category=kbo&playerId={pcode}"
    try:
        res = requests.get(url, headers=headers)
        data = res.json()

        if 'playerEndRecord' not in data or not data['playerEndRecord']:
            print(f"[{pcode}] No record data.")

        record_data = json.loads(data['playerEndRecord']['record'])
        season_data = record_data['season'][1]  # 최신 시즌 기준 (index 1)
        full_season_data = record_data['season'][0]

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

            era = full_season_data.get('era')
            w = full_season_data.get('w')
            l = full_season_data.get('l')
            sv = full_season_data.get('sv')
            war = full_season_data.get('war')

            Pitcher.objects.update_or_create(
                player=player,
                season=None,
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

            babip = full_season_data.get('babip')
            war = full_season_data.get('war')
            wrc = full_season_data.get('wrcPlus')

            Batter.objects.update_or_create(
                player=player,
                season=None,                
                defaults={
                    'babip': babip,
                    'war': war,
                    'wrc': wrc
                }
            )
            print(f"[{pcode}] Batter updated")
    
    except IndexError:
        print(f'[{pcode}] 1군 기록 없음')

    except Exception as e:
        print(f"[{pcode}] Error: {e}")

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
    
    today_stats = get_today_stat_from_redis(player) if player else None

    result = {
        "batter": direction,
        "season_2025": season_stats,
        "career": career_stats,
        "today": today_stats
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
                
                games = pitcher_obj.games or 0
                inn = pitcher_obj.innings or 0
                k = pitcher_obj.strikeouts or 0
                bb = pitcher_obj.walks or 0
                hits = (pitcher_obj.singles or 0) + (pitcher_obj.doubles or 0) + (pitcher_obj.triples or 0) + (pitcher_obj.homeruns or 0)
                
                # ERA 계산 (타점이 없으므로 0으로 설정)
                era = pitcher_obj.era or 0.0
                
                # K/9 계산
                k9 = round(k * 9.0 / inn, 2) if inn else 0.0
                
                # BB/9 계산
                bb9 = round(bb * 9.0 / inn, 2) if inn else 0.0
                
                # WHIP 계산
                whip = round((bb + hits) / inn, 2) if inn else 0.0
                
                return {
                    "games": games,
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

    today_stats = get_today_stat_from_redis(player) if player else None

    result = {
        "pitcher": [
            {"type": p['pit'], "rate": p['pit_rt'], "speed": p['speed']}
            for p in top_3
        ],
        "season_2025": season_stats,
        "career": career_stats,
        "today": today_stats
    }

    return result

def update_recent_5_stats_from_atbats(player):
    print(f"📊 [{player.player_name}] 최근 5경기 타수/안타 계산 시작")

    team_id = player.team_id
    pcode = player.pcode

    # ✅ 해당 팀의 최근 완료된 5경기
    recent_games = (
        Game.objects
        .filter(status='done')
        .filter(Q(home_team=team_id) | Q(away_team=team_id))
        .order_by('-date')[:5]
    )
    game_ids = [g.id for g in recent_games]

    # ✅ 해당 경기에서 타자가 나온 타석만 필터링
    atbats = AtBat.objects.filter(
        inning__game__id__in=game_ids,
        actual_player=pcode
    )

    # ✅ 타수 / 안타 계산
    ab = 0
    hits = 0

    for abt in atbats:
        is_ab = abt.main_result not in ['볼넷', '사구', '고의4구']
        is_hit = abt.main_result and any(hit in abt.main_result for hit in ['안타', '2루타', '3루타', '홈런'])

        if is_ab:
            ab += 1
        if is_hit:
            hits += 1

    # ✅ 가장 최신 Batter 객체 찾아서 저장
    latest_batter = (
        Batter.objects.filter(player=player, season__isnull=False)
        .order_by('-season')
        .first()
    )

    if latest_batter:
        BatterRecent.objects.update_or_create(
            batter=latest_batter,
            defaults={
                'ab': ab,
                'hits': hits,
                'updated_at': now()
            }
        )
        print(f"✅ 저장 완료: ab={ab}, hits={hits}")
    else:
        print("❌ Batter 객체 없음 (season 기록 없음)")