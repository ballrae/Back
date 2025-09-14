# services.py (완전 교체/대체 파일)
from django.db import transaction
from .models import Game, Inning, Player, AtBat, Pitch
from ballrae_backend.teams.models import Team
import json
from django.db.models import Q
from ballrae_backend.streaming.redis_client import redis_client
import requests
from datetime import datetime, timezone
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional

# ---------- 기존 get_stadium (변경 없음) ----------
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
    return team_to_stadium_map.get(team)

# ---------- 설정: 필요 시 조정 ----------
PLI_API_SINGLE_URL = "http://pli-api:8002/calculate_pli_raw"
PLI_API_BATCH_URL = "http://pli-api:8002/calculate_pli_raw_batch"  # pli-api에 배치 엔드포인트가 있다면 사용
PLI_CACHE_TTL = 60 * 60  # 초 (기본 1시간). 필요 시 줄이거나 늘리세요.
PARALLEL_WORKERS = 8      # 배치가 불가할 때 사용할 최대 스레드 수(pli-api에 부하를 고려해 적절히 설정)

# ---------- 캐시 키 생성 유틸 ----------
def _pli_cache_key(payload: dict, game_id: str) -> str:
    """
    PLI 캐시 키 생성. payload와 game_id에 기반.
    주의: payload는 PLI 계산에 영향을 주는 필드(타자, 투수, inning, count, runners 등)를 포함해야 함.
    """
    # json 정렬로 일관된 키 생성
    canonical = json.dumps({"game_id": game_id, **payload}, ensure_ascii=False, sort_keys=True)
    h = hashlib.sha1(canonical.encode()).hexdigest()
    return f"pli:{h}"

# ---------- 단일 호출: 기존 get_pli_from_api 동작 보존 + 캐시 ----------
def get_pli_from_api(atbat_data: dict, game_id: str, timeout: int = 5) -> Dict[str, Any]:
    """
    기존과 동일한 행동을 유지:
    - atbat_data에 team/stadium/streak 필드를 추가
    - 단일 PLI API 엔드포인트에 POST
    - 실패 시 {"error": "..."} 반환
    또한 결과를 Redis 캐시에 저장합니다.
    """
    # make a shallow copy to avoid mutating caller's dict unexpectedly? (원래는 in-place였음)
    payload = dict(atbat_data)

    # team 결정 (원래 로직 보존)
    offe_inn = game_id[8:10]
    if payload.get('half') == 'bot':
        offe_inn = game_id[10:12]

    payload['team'] = offe_inn
    payload['stadium'] = get_stadium(game_id[10:12])
    try:
        payload['streak'] = Team.objects.filter(id=offe_inn).values_list('consecutive_streak', flat=True).first()
    except Exception:
        payload['streak'] = None

    cache_key = _pli_cache_key(payload, game_id)
    cached = redis_client.get(cache_key)
    if cached:
        try:
            return json.loads(cached.decode() if isinstance(cached, bytes) else cached)
        except Exception:
            # 캐시가 손상되었으면 무시하고 새로 요청
            pass

    headers = {"Content-Type": "application/json"}
    try:
        resp = requests.post(PLI_API_SINGLE_URL, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        result = resp.json()
    except requests.exceptions.RequestException as e:
        print(f"Error calling PLI API (single): {e}")
        result = {"error": "Failed to get PLI from API"}

    # 캐시에 저장 (성공이든 실패 표식이든 저장해서 반복 실패로 인한 무한 요청 방지 가능)
    try:
        redis_client.setex(cache_key, PLI_CACHE_TTL, json.dumps(result, ensure_ascii=False))
    except Exception as e:
        print("Redis setex error (single):", e)

    return result

# ---------- 병렬 단일 호출 (배치 엔드포인트가 없을 때 사용되는 폴백) ----------
def _fetch_single_pli(payload: dict, game_id: str, timeout: int = 5) -> Dict[str, Any]:
    """internal helper: payload는 team/stadium/streak이 채워진 상태여야 함"""
    cache_key = _pli_cache_key(payload, game_id)
    cached = redis_client.get(cache_key)
    if cached:
        try:
            return json.loads(cached.decode() if isinstance(cached, bytes) else cached)
        except Exception:
            pass

    headers = {"Content-Type": "application/json"}
    try:
        r = requests.post(PLI_API_SINGLE_URL, headers=headers, json=payload, timeout=timeout)
        r.raise_for_status()
        res = r.json()
    except requests.exceptions.RequestException as e:
        print(f"Error calling PLI API (parallel single): {e}")
        res = {"error": "Failed to get PLI from API"}

    try:
        redis_client.setex(cache_key, PLI_CACHE_TTL, json.dumps(res, ensure_ascii=False))
    except Exception as e:
        print("Redis setex error (parallel single):", e)

    return res

# 교체할 get_pli_batch_and_cache 함수
def get_pli_batch_and_cache(atbats: List[dict], game_id: str, batch_timeout: int = 6) -> List[Dict[str, Any]]:
    """
    개선된/견고한 버전:
    - 원본 atbats는 즉시 수정하지 않음 (함수 끝에서 한 번에 부착)
    - 캐시 히트/미스 인덱스 매핑을 명확히 함
    - 배치 실패 시 병렬 폴백
    - 항상 atbats 길이와 같은 길이의 리스트 반환
    """
    n = len(atbats)
    # 결과 자리표시자
    results: List[Optional[Dict[str, Any]]] = [None] * n

    # 요청 대상 (캐시 미스)와 그 원래 인덱스를 보관
    to_request_payloads: List[dict] = []
    to_request_orig_indices: List[int] = []

    # 1) payload 준비 및 캐시 검사 (원본 atbat은 수정하지 않음)
    for idx, atbat in enumerate(atbats):
        payload = dict(atbat)  # shallow copy
        offe_inn = game_id[8:10]
        if payload.get('half') == 'bot':
            offe_inn = game_id[10:12]
        payload['team'] = offe_inn
        payload['stadium'] = get_stadium(game_id[10:12])
        try:
            payload['streak'] = Team.objects.filter(id=payload['team']).values_list('consecutive_streak', flat=True).first()
        except Exception:
            payload['streak'] = None

        cache_key = _pli_cache_key(payload, game_id)
        cached = redis_client.get(cache_key)
        if cached:
            try:
                results[idx] = json.loads(cached.decode() if isinstance(cached, bytes) else cached)
                continue
            except Exception:
                # 캐시 파싱 실패면 무시하고 요청 대상으로 넣음
                pass

        # 캐시 미스인 경우 요청 리스트 추가
        to_request_payloads.append(payload)
        to_request_orig_indices.append(idx)

    # 2) 배치 요청 (가능하면)
    if to_request_payloads:
        batch_succeeded = False
        try:
            batch_body = {"game_id": game_id, "atbats": to_request_payloads}
            headers = {"Content-Type": "application/json"}
            resp = requests.post(PLI_API_BATCH_URL, headers=headers, json=batch_body, timeout=batch_timeout)
            resp.raise_for_status()
            batch_res = resp.json()

            # 안전성 체크: 길이와 타입 확인
            if isinstance(batch_res, list) and len(batch_res) == len(to_request_payloads):
                # batch 결과를 원래 인덱스 위치에 채움
                for local_idx, res in enumerate(batch_res):
                    orig_idx = to_request_orig_indices[local_idx]
                    results[orig_idx] = res
                    # 캐시 저장 (payload는 to_request_payloads[local_idx])
                    try:
                        redis_client.setex(_pli_cache_key(to_request_payloads[local_idx], game_id), PLI_CACHE_TTL, json.dumps(res, ensure_ascii=False))
                    except Exception as e:
                        print("Redis setex error (batch store):", e)
                batch_succeeded = True
            else:
                raise ValueError("batch response invalid")
        except Exception as e:
            print("Batch call failed or invalid. Falling back to parallel single calls. Error:", e)
            batch_succeeded = False

        # 3) 배치 실패 시 병렬 단일 호출로 폴백
        if not batch_succeeded:
            # to_request_payloads와 to_request_orig_indices 길이는 동일
            max_workers = min(PARALLEL_WORKERS, max(1, len(to_request_payloads)))
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                future_to_local_idx = {}
                for local_idx, payload in enumerate(to_request_payloads):
                    future = ex.submit(_fetch_single_pli, payload, game_id)
                    future_to_local_idx[future] = local_idx

                for fut in as_completed(future_to_local_idx):
                    local_idx = future_to_local_idx[fut]
                    orig_idx = to_request_orig_indices[local_idx]
                    try:
                        res = fut.result()
                    except Exception as e2:
                        print("Parallel fetch exception:", e2)
                        res = {"error": "pli_fetch_failed"}
                    results[orig_idx] = res
                    # 캐시는 _fetch_single_pli 내부에서 이미 저장됨

    # 4) 모든 None은 에러 오브젝트로 채움
    for i, r in enumerate(results):
        if r is None:
            results[i] = {"error": "pli_unavailable"}

    # 5) 원본 atbats에 일괄적으로 pli_data 붙임 (호출자 코드와 동일한 결과 보장)
    for atbat, res in zip(atbats, results):
        atbat['pli_data'] = res

    return results

# ---------------------------------------------------------------------
# 아래는 기존에 있던 DB 저장/계산 함수들을 그대로 유지 (원본 코드 복붙)
# ---------------------------------------------------------------------

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