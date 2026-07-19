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

# =========================================================================
# Leverage Index (LI) — "이 타석이 승패를 얼마나 흔들 수 있나(변동성)"
# LI = Σ P(결과) × |WE(결과 후) − WE(현재)|  ÷  L_avg
# WE_MAP(승리기대 매트릭스)을 그대로 재사용한다. LI 는 타자 무관(맥락만)이므로
# 결과 확률은 리그평균 상수를 쓴다. 전이는 표준 단순 가정.
# =========================================================================

# 결과별 리그평균 확률 (per PA). 합 ≈ 1.0
_LI_OUTCOMES = {
    "out": 0.660,  # 삼진/범타 (병살·진루타 등 세부는 단순화)
    "bb":  0.090,  # 볼넷/사구 (강제 진루)
    "1b":  0.150,  # 단타
    "2b":  0.050,  # 2루타
    "3b":  0.005,  # 3루타
    "hr":  0.045,  # 홈런
}

# 승률(WP) 모델 로드 — 실측 WE 매트릭스가 후반/만루 셀에서 노이즈가 커서(표본 부족)
# LI 도출이 불가하므로, 전체 타석으로 학습한 매끄러운 로지스틱 WP 를 사용한다.
# 계수는 train_wp_model.py 로 학습해 data/wp_model.json 에 저장.
import math as _math
try:
    with open("data/wp_model.json") as _f:
        _WP = json.load(_f)
    _WP_W, _WP_B = _WP["weights"], _WP["bias"]
except Exception as _e:
    print("wp_model.json 로드 실패(WP=0.5 폴백):", _e)
    _WP_W, _WP_B = None, None


def _wp_features(inning, half, outs, r, sd):
    """train_wp_model.make_features 와 반드시 동일하게 유지."""
    outs = min(max(int(outs), 0), 2)
    inning = min(max(int(inning), 1), 11)
    prog = (((inning - 1) * 6) + (0 if half == "top" else 3) + outs) / 51.0
    bat_home = 1.0 if half == "bot" else 0.0
    base_threat = 0.9 * r[0] + 1.1 * r[1] + 1.3 * r[2]
    base_signed = base_threat * (1.0 if half == "bot" else -1.0)
    return [float(sd), float(sd) * prog, prog, bat_home, float(outs), base_signed]


def _we(inning, half, outs, r, sd):
    """학습된 로지스틱 WP(홈팀 승률). 항상 값을 반환(None 없음)."""
    if _WP_W is None:
        return 0.5
    f = _wp_features(inning, half, outs, r, sd)
    z = _WP_B + sum(wi * fi for wi, fi in zip(_WP_W, f))
    z = max(-30.0, min(30.0, z))
    return 1.0 / (1.0 + _math.exp(-z))


def _advance(outs, r, outcome):
    """표준 단순 전이. (new_outs, new_runners[3], 득점) 반환."""
    r1, r2, r3 = r
    if outcome == "out":
        return outs + 1, [r1, r2, r3], 0
    if outcome == "bb":  # 강제 진루만
        runs = 1 if (r1 and r2 and r3) else 0
        nr1 = 1
        nr2 = 1 if (r1 or r2) else 0
        nr3 = 1 if (r3 or (r1 and r2)) else 0
        return outs, [nr1, nr2, nr3], runs
    if outcome == "1b":  # 타자 1루, 주자 한 칸씩(3루 득점)
        return outs, [1, r1, r2], r3
    if outcome == "2b":  # 타자 2루, 주자 두 칸씩(2·3루 득점)
        return outs, [0, 1, r1], r2 + r3
    if outcome == "3b":  # 타자 3루, 전원 득점
        return outs, [0, 0, 1], r1 + r2 + r3
    if outcome == "hr":  # 타자 포함 전원 득점
        return outs, [0, 0, 0], r1 + r2 + r3 + 1
    return outs, [r1, r2, r3], 0


def _raw_leverage(inning, half, outs, r, sd):
    """현재 상태의 기대 WE 변동폭(정규화 전)."""
    we0 = _we(inning, half, outs, r, sd)
    if we0 is None:
        return None
    total = 0.0
    for oc, p in _LI_OUTCOMES.items():
        n_outs, nr, runs = _advance(outs, r, oc)
        if oc == "out" and n_outs >= 3:
            # 이닝 종료 → 다음 half/이닝, 0아웃 주자없음, 점수 동일
            if half == "top":
                we1 = _we(inning, "bot", 0, [0, 0, 0], sd)
            else:
                we1 = _we(inning + 1, "top", 0, [0, 0, 0], sd)
        else:
            # 공격팀 득점 → score_diff(홈-원정) 변화
            nsd = sd + runs if half == "bot" else sd - runs
            we1 = _we(inning, half, n_outs, nr, nsd)
        if we1 is None:
            we1 = we0  # 정보 없으면 변동 0 취급
        total += p * abs(we1 - we0)
    return total


def _compute_l_avg():
    # 모델 WP 위에서 현실적 상태 그리드(1~9회, sd -5~5)의 평균 변동폭으로 정규화.
    vals = []
    for inn in range(1, 10):
        for half in ("top", "bot"):
            for outs in range(3):
                for r1 in (0, 1):
                    for r2 in (0, 1):
                        for r3 in (0, 1):
                            for sd in range(-5, 6):
                                rl = _raw_leverage(inn, half, outs, [r1, r2, r3], sd)
                                if rl is not None:
                                    vals.append(rl)
    return (sum(vals) / len(vals)) if vals else 0.028


try:
    _L_AVG = _compute_l_avg()
    if not _L_AVG or _L_AVG <= 0:
        _L_AVG = 0.028
except Exception as _e:
    print("L_avg 계산 실패, 기본값 사용:", _e)
    _L_AVG = 0.028


def calc_leverage_index(inning, half, outs, runners_code, score_diff) -> float:
    """레버리지 인덱스. 평균 상황=1.0, High Leverage ≈ 1.5 이상."""
    try:
        runners = [1 if int(x) > 0 else 0 for x in str(runners_code)]
        runners = (runners + [0, 0, 0])[:3]
        rl = _raw_leverage(int(inning), half, int(outs), runners, int(score_diff))
        if rl is None:
            return 1.0
        return round(rl / _L_AVG, 2)
    except Exception as e:
        print("calc_leverage_index error:", e)
        return 1.0

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
# PLI = LI(레버리지) × 압박 가중치. 승부처(High LI)일수록, 압박이 클수록 높다.
# 반환: (pli, li, base_we, total_weight)  — base_we 는 참고용 승리기대(홈팀).
def calculate_single_pli(atbat_data: AtBatData):
    try:
        # 레버리지: "이 타석이 승패를 얼마나 흔드는가" (승부처 감지의 핵심)
        li = calc_leverage_index(
            atbat_data.inning, atbat_data.half, atbat_data.outs,
            atbat_data.runners_code, atbat_data.score_diff
        )

        # 참고용 승리기대(홈팀 관점) — 학습된 WP 모델
        _runners = [1 if int(x) > 0 else 0 for x in str(atbat_data.runners_code)]
        _runners = (_runners + [0, 0, 0])[:3]
        base_we = _we(atbat_data.inning, atbat_data.half, atbat_data.outs, _runners, atbat_data.score_diff)

        # 압박(Pressure) 가중치
        w_env = batting_weather_weight(atbat_data.temp_c)
        w_personal = combine_weights(calculate_condition(atbat_data.batter_id, atbat_data.pitcher))
        w_situ = combine_weights(
            streak_weight(atbat_data.loss_streak), pinch_weight(atbat_data.pinch_event),
            ibb_focus_weight(atbat_data.intentional_walk),
            error_momentum_weight(atbat_data.error_happened, atbat_data.next_batter_after_error)
        )
        w_total = combine_weights(w_env, w_personal, w_situ)

        # PLI = 레버리지 × 압박 (레버리지는 좌우 대칭 → top/bot 플립 불필요)
        pli_val = round(li * w_total, 4)
        return pli_val, round(li, 2), round(float(base_we), 4), w_total
    except Exception as e:
        print("calculate_single_pli error:", e)
        # 언패킹 실패로 상위에서 500 나지 않도록 중립값 폴백
        return 1.0, 1.0, 0.5, 1.0

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