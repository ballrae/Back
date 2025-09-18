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
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
# 타임아웃/병렬 관련 설정 — 운영환경에 맞게 조정 가능
PARALLEL_WORKERS = 3        # 병렬 호출 수를 많이 낮춤 (원래 8 → 3 권장)
PLI_API_SINGLE_URL = "http://pli-api:8002/calculate_pli_raw"
PLI_API_JOB_URL = "http://pli-api:8002/job"
PLI_CACHE_TTL = 60 * 60     # 정상 결과 TTL
PLI_ERROR_TTL = 10          # 에러는 짧게 캐시
REQUEST_TIMEOUT = 15        # individual request read timeout (초) — 6 → 15로 증가
MAX_RETRIES = 2             # 네트워크/일시오류 시 재시도 횟수 (총 시도 = MAX_RETRIES + 1)
BACKOFF_FACTOR = 0.5        # 지수 백오프 계수 (0.5, 1, 2 초 등)
LOCK_TTL = 8                # singleflight 락 TTL (초)
JOB_POLLING_TIMEOUT = 30  # job 결과 대기 시간
JOB_POLLING_INTERVAL = 0.5  # polling 간격

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
    
    print(payload)

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
        result = {"error": "Failed to get PLI from API", "pli": None, "base_we": None, "total_weight": None}

    # 캐시에 저장 (성공이든 실패 표식이든 저장해서 반복 실패로 인한 무한 요청 방지 가능)
    try:
        redis_client.setex(cache_key, PLI_CACHE_TTL, json.dumps(result, ensure_ascii=False))
    except Exception as e:
        print("Redis setex error (single):", e)

    return result

def _requests_session_with_retries(total_retries=MAX_RETRIES, backoff_factor=BACKOFF_FACTOR):
    session = requests.Session()
    retries = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["POST", "GET", "OPTIONS"])
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def _acquire_lock(cache_key: str, wait_max=3.0, step=0.05):
    lock_key = f"lock:{cache_key}"
    start = time.time()
    got = redis_client.set(lock_key, "1", nx=True, ex=LOCK_TTL)
    if got:
        return True
    while time.time() - start < wait_max:
        time.sleep(step)
        # 누군가 작업 완료해서 캐시가 생겼다면 대기 중단
        if redis_client.get(cache_key):
            return False
        got = redis_client.set(lock_key, "1", nx=True, ex=LOCK_TTL)
        if got:
            return True
    # 마지막 시도
    got = redis_client.set(lock_key, "1", nx=True, ex=LOCK_TTL)
    return bool(got)

def _release_lock(cache_key: str):
    try:
        redis_client.delete(f"lock:{cache_key}")
    except Exception:
        pass

def _fetch_single_pli(payload: dict, game_id: str, timeout: int = REQUEST_TIMEOUT) -> Dict[str, Any]:
    """
    안전한 단일 PLI 호출:
    - 캐시 체크
    - singleflight 락으로 중복 요청 억제
    - requests.Session + Retry 사용 (총 MAX_RETRIES 재시도)
    - 응답 지연 시 timeout을 늘려 기다림
    - 성공만 장기 캐시, 에러는 짧게 혹은 캐시하지 않음
    """
    cache_key = _pli_cache_key(payload, game_id)

    # 1) 캐시 우선 확인
    cached = redis_client.get(cache_key)
    if cached:
        try:
            print(json.loads(cached.decode() if isinstance(cached, bytes) else cached))
            return json.loads(cached.decode() if isinstance(cached, bytes) else cached)
        except Exception:
            pass

    # 2) singleflight 락 시도: 락을 얻으면 우리가 호출, 못 얻으면 캐시 채워질 때까지 기다렸다가 캐시 쓰기
    got_lock = _acquire_lock(cache_key)
    if not got_lock:
        # 누군가 채우는 중이면 캐시 재확인
        cached = redis_client.get(cache_key)
        if cached:
            try:
                print(json.loads(cached.decode() if isinstance(cached, bytes) else cached))
                return json.loads(cached.decode() if isinstance(cached, bytes) else cached)
            except Exception:
                pass
        # 락 못 얻고 캐시도 없으면 마지막 수단으로 호출 시도 (but still limited)
        # continue to call

    session = _requests_session_with_retries()
    headers = {"Content-Type": "application/json"}

    try:
        # 디버그 로그 (운영시엔 level 체크해서 끌 것)
        try:
            print("PLI CALL payload:", json.dumps(payload, ensure_ascii=False))
        except Exception:
            print("PLI CALL payload (unserializable)")

        resp = session.post(PLI_API_SINGLE_URL, headers=headers, json=payload, timeout=timeout)
        # 상태/본문 로그 (디버그)
        print("PLI CALL status:", getattr(resp, "status_code", None))
        try:
            text = resp.text
            print("PLI CALL resp text len:", len(text))
        except Exception:
            text = None

        resp.raise_for_status()
        result = resp.json()
    except requests.exceptions.RequestException as e:
        print("Error calling PLI API (single, retry enabled):", repr(e))
        # 실패 시 짧게 캐시(혹은 캐시하지 않음)
        error_obj = {"error": "Failed to get PLI from API", "detail": str(e)}
        try:
            redis_client.setex(cache_key, PLI_ERROR_TTL, json.dumps(error_obj, ensure_ascii=False))
        except Exception:
            pass
        result = error_obj
    finally:
        # 락 해제 (락을 획득했든 못 했든 안전하게 호출)
        try:
            _release_lock(cache_key)
        except Exception:
            pass

    # 성공이면 장기 캐시
    if isinstance(result, dict) and "error" not in result:
        try:
            redis_client.setex(cache_key, PLI_CACHE_TTL, json.dumps(result, ensure_ascii=False))
        except Exception as e:
            print("Redis setex error after success:", e)

    return result

def get_pli_batch_and_cache(atbats: List[dict], game_id: str, timeout_per_request: int = REQUEST_TIMEOUT) -> List[Dict[str, Any]]:
    n = len(atbats)
    results: List[Optional[Dict[str, Any]]] = [None] * n
    to_request_payloads: List[dict] = []
    to_request_indices: List[int] = []

    # 1) payload 준비 및 캐시 검사
    for idx, atbat in enumerate(atbats):
        payload = dict(atbat)
        offe_inn = game_id[8:10]
        if payload.get('half') == 'bot':
            offe_inn = game_id[10:12]

        # pitch_sequence == None → 대타 상황 → PLI 계산 생략
        if payload.get('strike_zone') is None:
            results[idx] = None  # 명시적으로 None 저장
            continue

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
                pass
        to_request_payloads.append(payload)
        to_request_indices.append(idx)

    # 2) 캐시 미스만 병렬 호출 (스레드풀)
    if to_request_payloads:
        max_workers = min(PARALLEL_WORKERS, max(1, len(to_request_payloads)))
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            future_to_local_idx = {}
            for local_idx, payload in enumerate(to_request_payloads):
                future = ex.submit(_fetch_single_pli, payload, game_id, timeout_per_request)
                future_to_local_idx[future] = local_idx
            for fut in as_completed(future_to_local_idx):
                local_idx = future_to_local_idx[fut]
                orig_idx = to_request_indices[local_idx]
                try:
                    res = fut.result()
                except Exception as e:
                    print("Parallel fetch exception:", e)
                    res = {"error": "Failed to get PLI from API", "pli": None, "base_we": None, "total_weight": None}
                results[orig_idx] = res

    # 3) None 채우기 (단, pitch_sequence==None 은 그대로 둠)
    for i, r in enumerate(results):
        if atbats[i].get('strike_zone') is None:
            results[i] = {"pli": "unavailable"}
        elif r is None and atbats[i].get('pitch_sequence') is not None:
            results[i] = {"error": "pli_unavailable"}

    # 4) atbat에 부착
    for atbat, res in zip(atbats, results):
        atbat['pli_data'] = res

    return results

@transaction.atomic
def save_at_bat_transactionally(data: dict, game_id, merged_dict):
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
                actual_batter = atbat.get('actual_batter')
                batter, _ = Player.objects.get_or_create(
                    pcode=actual_batter,
                    position='B',
                    team_id=b_id,
                    player_name = merged_dict.get(actual_batter)
                )

                # 투수 이름 가져오기
                pitcher, _ = Player.objects.get_or_create(
                    pcode=atbat.get('pitcher'),
                    position='P',
                    team_id=p_id,
                    player_name = merged_dict.get(atbat.get('pitcher'))
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

# services.py에 추가할 함수들

def get_pli_from_api_with_job(atbat_data: dict, game_id: str, timeout: int = 30) -> Dict[str, Any]:
    """
    RQ job을 사용한 비동기 PLI 계산
    - 즉시 job_id 반환
    - 결과는 별도로 polling 필요
    """
    payload = dict(atbat_data)
    
    # team/stadium/streak 추가 (기존과 동일)
    offe_inn = game_id[8:10]
    if payload.get('half') == 'bot':
        offe_inn = game_id[10:12]
    
    payload['team'] = offe_inn
    payload['stadium'] = get_stadium(game_id[10:12])
    try:
        payload['streak'] = Team.objects.filter(id=offe_inn).values_list('consecutive_streak', flat=True).first()
    except Exception:
        payload['streak'] = None
    
    headers = {"Content-Type": "application/json"}
    try:
        # job 생성 요청
        resp = requests.post(PLI_API_SINGLE_URL, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        job_data = resp.json()
        return {"job_id": job_data["job_id"], "status": "queued"}
    except requests.exceptions.RequestException as e:
        print(f"Error creating PLI job: {e}")
        return {"error": "Failed to create PLI job", "detail": str(e)}

def get_pli_job_result(job_id: str, timeout: int = 5) -> Dict[str, Any]:
    """
    RQ job 결과 조회
    """
    try:
        resp = requests.get(f"{PLI_API_JOB_URL}/{job_id}", timeout=timeout)
        if resp.status_code == 404:
            # 엔드포인트는 있으나 아직 해당 job이 레디스에 반영되지 않은 초기 상태일 수 있음
            return {"status": "pending"}
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching job result: {e}")
        return {"error": "Failed to fetch job result", "detail": str(e)}

def get_pli_batch_with_jobs(atbats: List[dict], game_id: str) -> List[Dict[str, Any]]:
    """
    RQ job을 사용한 배치 PLI 계산
    - 모든 atbat에 대해 job 생성
    - 결과를 polling해서 수집
    """
    n = len(atbats)
    results: List[Optional[Dict[str, Any]]] = [None] * n
    job_ids: List[Optional[str]] = [None] * n
    
    # 1) 모든 atbat에 대해 job 생성
    for idx, atbat in enumerate(atbats):
        if atbat.get('strike_zone') is None:
            results[idx] = {"pli": "unavailable"}
            continue
            
        job_result = get_pli_from_api_with_job(atbat, game_id)
        if "job_id" in job_result:
            job_ids[idx] = job_result["job_id"]
        else:
            results[idx] = job_result
    
    # 2) job 결과 polling (최대 30초)
    max_wait = 30
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        all_done = True
        for idx, job_id in enumerate(job_ids):
            if job_id is None or results[idx] is not None:
                continue
                
            job_result = get_pli_job_result(job_id)
            if job_result.get("status") == "finished":
                results[idx] = job_result.get("result", {})
            elif job_result.get("status") == "failed":
                results[idx] = {"error": "Job failed", "detail": job_result.get("error")}
            else:
                all_done = False
        
        if all_done:
            break
        time.sleep(0.5)  # 500ms 대기
    
    # 3) 미완료 job 처리
    for idx, job_id in enumerate(job_ids):
        if job_id is not None and results[idx] is None:
            results[idx] = {"error": "Job timeout"}
    
    # 4) atbat에 부착
    for atbat, res in zip(atbats, results):
        atbat['pli_data'] = res
    
    return results