import pandas as pd
from pydantic import BaseModel
from typing import Optional
import requests
import pytz
from datetime import datetime, timedelta
import ast
import requests
import json

# --- 1. 데이터 로딩 (서버 시작 시 한 번만 실행) ---
try:
    wpa_data = pd.read_csv('data/kbo_we_matrix_filtered.csv')
    stadium_data = pd.read_csv('data/stadium.csv')
    
    WE_MAP = {
        (row['inning_number'], row['half'], row['out'], row['runner_on_1b'], row['runner_on_2b'], row['runner_on_3b'], row['score_diff']): row['win_expectancy']
        for _, row in wpa_data.iterrows()
    }
    stadium_data["weather"] = stadium_data["weather"].apply(
        lambda x: ast.literal_eval("{" + x + "}") if isinstance(x, str) and "nx" in x else None
    )
    STADIUM_MAP = {
        row["scode"]: {
            "name": row["stadium"], "reg_id": row["REG_ID"], "grid": row["weather"], "parkfactor": row["parkfactor"], "city": row["city"],
        }
        for _, row in stadium_data.iterrows()
    }

except FileNotFoundError:
    raise FileNotFoundError("Data files not found.")

# --- 2. PLI 계산에 필요한 보조 함수들 ---
def get_win_expectancy(inning, half, outs, runners_code, score_diff):
    runners = [1 if int(r) > 0 else 0 for r in runners_code]
    key = (inning, half, outs, runners[0], runners[1], runners[2], score_diff)
    # print(key)
    we = WE_MAP.get(key, None)
    return we

def combine_weights(*weights):
    total_weight = 1.0
    for w in weights:
        if w is not None: total_weight *= w
    return total_weight

def calculate_situation_level(inning, outs, runners_code, score_diff):
    total_score = 0
    if inning >= 9: total_score += 3
    elif inning == 8: total_score += 2
    elif inning == 7: total_score += 1
    if outs == 0: total_score += 2
    elif outs == 1: total_score += 1
    runner_scores = {'000': 0, '100': 1, '010': 2, '110': 2, '001': 3, '101': 3, '011': 3, '111': 3}
    total_score += runner_scores.get(runners_code, 0)
    abs_score_diff = abs(score_diff)
    if abs_score_diff == 0: total_score += 3
    elif abs_score_diff == 1: total_score += 2
    elif abs_score_diff <= 3: total_score += 1
    if total_score >= 9: description = "최대 위기/방화"
    elif total_score >= 6: description = "중요한 승부처"
    elif total_score >= 3: description = "관리 필요"
    else: description = "일상적 교체"
    return (total_score, description)

def batting_weather_weight(temp_c: float | None, base_temp: float = 22.0, alpha: float = 0.02) -> float:
    if temp_c is None or temp_c <= base_temp: return 1.0
    return 1.0 + (temp_c - base_temp) * alpha

def _kma_base_datetime_now_kst():
    kst = pytz.timezone("Asia/Seoul")
    now = datetime.now(kst)
    if now.minute < 45: now = now - timedelta(hours=1)
    base_time_map = {2:'0200',5:'0500',8:'0800',11:'1100',14:'1400',17:'1700',20:'2000',23:'2300'}
    hours = [h for h in base_time_map if h <= now.hour]
    if not hours:
        now = now - timedelta(days=1)
        base_time = '2300'
    else:
        base_time = base_time_map[max(hours)]
    base_date = now.strftime('%Y%m%d')
    return base_date, base_time

# 기상청 예보는 시간당 1회만 실제 호출하고 Redis에 캐싱해서 재사용 (설계 의도).
# 매 타석마다 기상청을 때리지 않도록 (구장·예보시각·발표시각) 단위로 캐시.
try:
    from rq_queue import redis_client as _weather_redis
except Exception:
    _weather_redis = None

WEATHER_TTL = 3600  # 1시간


def get_stadium_temperature(scode: str, target_hour: int, *, auth_key: str, timeout: int = 10) -> float | None:
    info = STADIUM_MAP.get(scode.upper())
    if not info or not info["grid"]: return None
    base_date, base_time = _kma_base_datetime_now_kst()
    target_time_str = f"{target_hour:02d}00"

    cache_key = f"weather:{scode.upper()}:{target_time_str}:{base_date}:{base_time}"
    if _weather_redis is not None:
        try:
            hit = _weather_redis.get(cache_key)
            if hit is not None:
                return None if hit == "None" else float(hit)
        except Exception:
            pass

    params = {
        "authKey": auth_key, "pageNo": "1", "numOfRows": "1000", "dataType": "JSON", "base_date": base_date, "base_time": base_time, "nx": str(info["grid"]["nx"]), "ny": str(info["grid"]["ny"]),
    }
    url = "https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/getVilageFcst"
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        items = data["response"]["body"]["items"]["item"]
        tmp_val = None
        for it in items:
            if it.get("category") == "TMP" and it.get("fcstTime") == target_time_str:
                tmp_val = float(it.get("fcstValue"))
                break
    except Exception as e:
        print(f"Error fetching weather data: {e}")
        tmp_val = None

    # 성공/실패 모두 캐시 (실패도 시간당 재시도 억제; 매 타석 재호출 방지)
    if _weather_redis is not None:
        try:
            _weather_redis.setex(cache_key, WEATHER_TTL, "None" if tmp_val is None else str(tmp_val))
        except Exception:
            pass
    return tmp_val

CONDITION_TTL = 3600  # 컨디션은 (타자,투수) 매치업 단위로 시간당 캐시


def calculate_condition(pcode: str, pitcher: str):
    """
    타자의 시즌/최근 타율로 컨디션 가중치 계산.
    realtime 엔드포인트가 내부에서 네이버 API를 타서 느리므로,
    매 타석 재호출을 막기 위해 (타자,투수) 매치업 결과를 Redis에 캐시한다.
    (설계 의도: 외부 의존 값은 캐싱해서 실시간 서빙 hot-path를 가볍게)
    """
    cache_key = f"condition:{pcode}:{pitcher}"
    if _weather_redis is not None:
        try:
            hit = _weather_redis.get(cache_key)
            if hit is not None:
                return float(hit)
        except Exception:
            pass

    final_weight = 1.0
    try:
        url = f"http://ballrae-backend:8000/api/players/realtime/?batter={pcode}&pitcher={pitcher}"
        response = requests.get(url, timeout=2)  # hot-path 이므로 짧게
        if response.status_code == 200:
            data = response.json()
            # 실제 응답 구조: {"data": {"batter": {"season_2025": {"avg": ...}, "recent_stats": <float>}}}
            batter = (data.get("data") or {}).get("batter") or {}
            season = batter.get("season_2025") or {}
            season_avg = season.get("avg") if isinstance(season, dict) else None
            recent_avg = batter.get("recent_stats")
            if season_avg and recent_avg and season_avg != 0:
                condition_index = recent_avg / season_avg
                final_weight = 1.0 + (condition_index - 1.0) * 0.5
        else:
            print(f"컨디션 API 호출 실패: status={response.status_code}")
    except Exception as e:
        print(f"컨디션 API 호출 중 오류: {e}")

    # 성공/실패(1.0 폴백) 모두 캐시 → 같은 매치업 재호출 방지
    if _weather_redis is not None:
        try:
            _weather_redis.setex(cache_key, CONDITION_TTL, str(final_weight))
        except Exception:
            pass
    return final_weight

def streak_weight(loss_streak):
    if loss_streak is None or loss_streak <= 2: return 1.0
    elif 3 <= loss_streak <= 4: return 0.95
    elif 5 <= loss_streak <= 6: return 0.90
    else: return 0.85

def pinch_weight(is_pinch_hitter): return 1.5 if is_pinch_hitter else 1.0

def ibb_focus_weight(is_ibb): return 2.0 if is_ibb else 1.0

def error_momentum_weight(is_error, is_next_batter):
    if is_error and is_next_batter: return 1.2
    return 1.0

# --- 3. API 요청 데이터 모델 정의 ---
class AtBatData(BaseModel):
    inning: int
    half: str
    outs: int
    runners_code: str
    score_diff: int
    batter_id: str
    stadium_code: Optional[str] = None
    temp_c: Optional[float] = None
    loss_streak: Optional[int] = None
    pinch_event: bool = False
    intentional_walk: bool = False
    error_happened: bool = False
    next_batter_after_error: bool = False
    pitcher: str

# --- 4. PLI 계산 핵심 로직 ---
def calculate_single_pli(atbat_data: AtBatData):
    try:
        we_end = get_win_expectancy(
            atbat_data.inning, atbat_data.half, atbat_data.outs, atbat_data.runners_code, atbat_data.score_diff
        )
        base_we = we_end if we_end is not None else 0.5
        
        w_env = batting_weather_weight(atbat_data.temp_c)
        w_personal = combine_weights(calculate_condition(atbat_data.batter_id, atbat_data.pitcher))
        w_situ = combine_weights(
            streak_weight(atbat_data.loss_streak), pinch_weight(atbat_data.pinch_event),
            ibb_focus_weight(atbat_data.intentional_walk),
            error_momentum_weight(atbat_data.error_happened, atbat_data.next_batter_after_error)
        )
        w_total = combine_weights(w_env, w_personal, w_situ)
        pli_val = round(float(base_we) * w_total, 4)

        if atbat_data.half == "top":
            return (1-pli_val), (1-base_we), w_total
        else:
            return pli_val, base_we, w_total
    except Exception as e:
        print("calculate_single_pli error:", e)
        # 언패킹 실패(None 반환)로 상위에서 500 나지 않도록 중립값 폴백
        return 0.5, 0.5, 1.0

# --- 8. 원본 데이터 가공 함수 (모든 가중치 함수 호출) ---
def process_raw_atbat_data(raw_data) -> dict:
    global next_error 
    next_error = False

    if type(raw_data) == str:
        raw_data = json.loads(raw_data)

    # 라이브 데이터는 필드가 None/형식 불일치인 타석이 종종 있으므로 방어적으로 파싱.
    try:
        outs = int(raw_data.get("out") or 0)
    except (TypeError, ValueError):
        outs = 0

    score_str = raw_data.get("score") or "0:0"
    try:
        away_score, home_score = map(int, str(score_str).split(':'))
    except Exception:
        away_score, home_score = 0, 0
    score_diff = home_score - away_score

    on_base = raw_data.get("on_base")
    if not isinstance(on_base, dict):
        on_base = {"base1": "0", "base2": "0", "base3": "0"}
    runners_code = f"{on_base.get('base1', 0)}{on_base.get('base2', 0)}{on_base.get('base3', 0)}"

    batter_pcode = raw_data.get("actual_batter")
    main_result = raw_data.get("main_result") or ""
    full_result = raw_data.get("full_result") or ""
    pitcher = raw_data.get("pitcher")

    next_batter_after_error = next_error or False

    stadium_code = raw_data.get("stadium")
    loss_streak = raw_data.get("streak")
    combined_result = main_result or full_result
    pinch_event = '대타' in combined_result
    intentional_walk = '고의 4구' in main_result
    error_happened = '실책' in combined_result

    # 전역 변수로 next_error 상태를 저장하여 다음 함수 호출 시에도 사용할 수 있도록 함
    # 함수 외부에서 선언된 전역 변수를 수정
    if error_happened: 
        next_error = True
    else: 
        next_error = False
    
    # 실제 온도 가져오기
    WEATHER_API_KEY = 'iVHg1Rm_SGuR4NUZv3hrLw'
    weather_temp = get_stadium_temperature(stadium_code, target_hour=datetime.now().hour, auth_key=WEATHER_API_KEY)

    return {
        "inning": int(raw_data.get("inning") or 0),
        "half": raw_data.get("half") or "top",
        "outs": outs,
        "score_diff": score_diff,
        "runners_code": runners_code,
        "batter_id": str(batter_pcode) if batter_pcode is not None else "",
        "stadium_code": stadium_code,
        "temp_c": weather_temp,
        "loss_streak": loss_streak,
        "pinch_event": pinch_event,
        "intentional_walk": intentional_walk,
        "error_happened": error_happened,
        "next_batter_after_error": next_batter_after_error,
        "pitcher": str(pitcher) if pitcher is not None else "",
    }