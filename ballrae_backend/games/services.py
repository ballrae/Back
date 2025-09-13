from django.db import transaction
from .models import Game, Inning, Player, AtBat, Pitch
from ballrae_backend.teams.models import Team
import json
from django.db.models import Q
from ballrae_backend.streaming.redis_client import redis_client
import requests
from datetime import datetime, timezone
from ballrae_backend.teams.models import Team

def get_stadium(team):
    # 팀 코드를 스타디움 코드로 매핑하는 딕셔너리
    team_to_stadium_map = {
        "LG": "JS",  # LG 트윈스 - 잠실야구장
        "KT": "SW",  # KT 위즈 - 수원KT위즈파크
        "SL": "MH",  # SSG 랜더스 - 인천SSG랜더스필드
        "NC": "CW",  # NC 다이노스 - 창원NC파크
        "DS": "JS",  # 두산 베어스 - 잠실야구장
        "KA": "GJ",  # KIA 타이거즈 - 광주기아챔피언스필드
        "LT": "SJ",  # 롯데 자이언츠 - 부산사직야구장
        "SS": "DG",  # 삼성 라이온즈 - 대구삼성라이온즈파크
        "HH": "DJ",  # 한화 이글스 - 대전한화생명이글스파크
        "HE": "GC",  # 키움 히어로즈 - 고척스카이돔
    }
    
    return team_to_stadium_map.get(team)  # 기본값은 잠실야구장

def get_pli_from_api(atbat_data: dict, game_id: str):
    """
    pli-api 컨테이너로 HTTP POST 요청을 보내 PLI 값을 받아옵니다.
    """
    api_url = "http://pli-api:8002/calculate_pli_raw"
    headers = {"Content-Type": "application/json"}

    offe_inn = game_id[8:10]
    if atbat_data.get('half') == 'bot': offe_inn = game_id[10:12]

    streak = Team.objects.filter(id=offe_inn).values_list('consecutive_streak', flat=True).first()

    atbat_data['team'] = offe_inn
    atbat_data['stadium'] = get_stadium(game_id[10:12])
    atbat_data['streak'] = streak
    
    try:
        response = requests.post(api_url, headers=headers, json=atbat_data, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error calling PLI API: {e}")
        return {"error": "Failed to get PLI from API"}

@transaction.atomic
def save_at_bat_transactionally(data: dict, game_id):
    atbat_data = data['at_bats']

    game, _ = Game.objects.get_or_create(id=game_id)

    inning, _ = Inning.objects.get_or_create(
        game=game,
        inning_number=data['inning'],
        half=data.get('half', 'top')
    )

    for atbat in atbat_data:
        try:
            if inning.half == 'top': b_id = game_id[8:10]; p_id = game_id[10:12]
            else: b_id = game_id[10:12]; p_id = game_id[8:10]
            pitcher = atbat.get('pitcher', [])

            if pitcher:
                batter, _ = Player.objects.get_or_create(
                    position='B',
                    team_id=b_id,
                    pcode=atbat.get('actual_batter')
                )

                pitcher, _ = Player.objects.get_or_create(
                    position='P',
                    team_id=p_id,
                    pcode=atbat.get('pitcher')
                )
        
            exists = AtBat.objects.filter(
                inning=inning,
                actual_player=atbat.get('actual_batter'),
                bat_order=atbat.get('bat_order'),
                appearance_num=atbat.get('appearance_number', 1)
            ).exists()

            if exists:
                print(f"이미 저장된 타석: {atbat.get('actual_batter')} #{atbat.get('appearance_number')}")
                continue

            # 새 타석 저장
            at_bat = AtBat.objects.create(
                inning=inning,
                bat_order=atbat.get('bat_order'),
                pitcher=atbat.get('pitcher'),
                out=atbat.get('out'),
                score=atbat.get('score'),
                on_base=atbat.get('on_base'),
                strike_zone=atbat.get('strike_zone'),
                main_result=atbat.get('main_result'),
                full_result=atbat.get('full_result'),
                original_player=atbat.get('original_batter'),
                actual_player=atbat.get('actual_batter'),
                appearance_num=atbat.get('appearance_number', 1)
            )

            pitches_data = atbat.get("pitch_sequence", [])

            if pitches_data:
                for pitch in pitches_data:
                    Pitch.objects.get_or_create(
                        at_bats=at_bat,
                        pitch_num=pitch['pitch_num'],
                        pitch_type=pitch.get('pitch_type'),
                        speed=pitch.get('speed'),
                        count=pitch.get('count'),
                        pitch_coordinate=pitch.get('pitch_coordinate'),
                        event=pitch.get('event'),
                        pitch_result=pitch.get('pitch_result')
                    )
        except:
            print(game, inning, batter.player_name, "error")
            continue

def get_score_from_atbats(game_id):
    keys = redis_client.keys(f"game:{game_id}*")

    # 이닝과 half 추출 함수
    def extract_inning_and_half(key):
        try:
            parts = key.split(":")
            inning = int(parts[-2])
            half = parts[-1]
            return inning, half
        except Exception:
            return -1, ""

    inning_half_list = []
    for key in keys:
        k = key.decode() if isinstance(key, bytes) else key
        inning, half = extract_inning_and_half(k)
        if inning != -1:
            inning_half_list.append((inning, half, k))

    if not inning_half_list:
        return None

    max_inning = max(inning_half_list, key=lambda x: x[0])[0]
    max_inning_keys = [(half, k) for inning, half, k in inning_half_list if inning == max_inning]

    valid_key = None
    for half, k in max_inning_keys:
        if half == "bot":
            valid_key = k
            break
    if not valid_key:
        for half, k in max_inning_keys:
            if half == "top":
                valid_key = k
                break

    recent = json.loads(redis_client.get(valid_key))['atbats'][-1]['score']
    return recent

# =========================
# 팀별 승/패/연승연패 계산 함수
# =========================

@transaction.atomic
def update_team_wins_loses_and_streak():
    """
    2025-03-22 이후의 done 경기들에 대해 각 팀의 승/패/연승연패(streak) 정보를 계산해서 Team 테이블에 저장합니다.
    """
    기준일 = datetime(2025, 3, 22, tzinfo=timezone.utc)
    # 모든 팀의 승/패/연승연패 초기화
    for team in Team.objects.all():
        team.wins = 0
        team.loses = 0
        team.consecutive_streak = 0
        team.save()

    # 각 팀별로 경기 결과를 시간순으로 모음
    team_results = {}  # team_id: [("W" or "L"), ...] (시간순)
    teams = {t.id: t for t in Team.objects.all()}

    # done이고 기준일 이후 경기만
    games = Game.objects.filter(status='done', date__gte=기준일).order_by('date', 'id')

    for game in games:
        # 스코어가 없으면 스킵
        if not game.score or ':' not in game.score:
            continue

        # away, home 팀 id
        away = game.away_team
        home = game.home_team

        try:
            away_score, home_score = map(int, game.score.split(":"))
        except Exception:
            continue

        # 승패 결정
        if away_score > home_score:
            winner, loser = away, home
        elif home_score == away_score:
            winner, loser = None, None
        else:
            winner, loser = home, away

        # 결과 기록
        for tid in [away, home]:
            if tid not in team_results:
                team_results[tid] = []
        if winner == away:
            team_results[away].append("W")
            team_results[home].append("L")
        elif winner == None:
            team_results[away].append("T")
            team_results[home].append("T")
        else:
            team_results[away].append("L")
            team_results[home].append("W")

    # 각 팀별로 승/패/연승연패(streak) 계산
    for tid, results in team_results.items():
        team = teams.get(tid)
        if not team:
            continue
        team.wins = results.count("W")
        team.loses = results.count("L")
        team.tie = results.count("T")

        # streak 계산 (가장 최근 경기부터 연속된 W/L 개수)
        streak = 0
        if results:
            last = results[-1]
            for r in reversed(results):
                if r == last:
                    streak += 1
                else:
                    break
            if last == "L":
                streak = -streak  # 연패는 음수
        team.consecutive_streak = streak
        team.save()

    print("팀별 승/패/연승연패(streak) 업데이트 완료")