import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import requests
import pytz
from datetime import datetime, timedelta
import ast
import os
import django

# --- 1. 데이터 로딩 (서버 시작 시 한 번만 실행) ---
try:
    wpa_data = pd.read_csv('data/kbo_we_matrix_filtered.csv')
    stadium_data = pd.read_csv('data/stadium.csv')
    
    WE_MAP = {
        (row['inning_number'], row['half'] == 'bot', row['out'], row['runner_on_1b'], row['runner_on_2b'], row['runner_on_3b'], row['score_diff']): row['win_expectancy']
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

# --- Django 모델 로딩 (DB 연동을 위해 필요) ---
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ballrae_backend.settings')
django.setup()
from ballrae_backend.players.models import Batter, BatterRecent

# --- 2. PLI 계산에 필요한 보조 함수들 ---
def get_win_expectancy(inning, half, outs, runners_code, score_diff):
    is_home = (half == 'bot')
    runners = [int(r) for r in runners_code]
    key = (inning, is_home, outs, runners[0], runners[1], runners[2], score_diff)
    return WE_MAP.get(key, None)

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

def get_stadium_temperature(scode: str, target_hour: int, *, auth_key: str, timeout: int = 10) -> float | None:
    info = STADIUM_MAP.get(scode.upper())
    if not info or not info["grid"]: return None
    base_date, base_time = _kma_base_datetime_now_kst()
    target_time_str = f"{target_hour:02d}00"
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
        return tmp_val
    except Exception as e:
        print(f"Error fetching weather data: {e}")
        return None

def calculate_condition(pcode: str, season: int = 2025):
    try:
        batter = Batter.objects.get(player__pcode=pcode, season=season)
        recent = BatterRecent.objects.get(batter=batter)
        if batter.ab == 0 or recent.ab == 0: return 1.0
        season_avg = batter.hits / batter.ab
        recent_avg = recent.hits / recent.ab
        beta = 0.5
        condition_index = recent_avg / season_avg
        final_weight = 1.0 + (condition_index - 1.0) * beta
        return final_weight
    except (Batter.DoesNotExist, BatterRecent.DoesNotExist): return 1.0
    except ZeroDivisionError: return 1.0
    except Exception as e:
        print(f"Error calculating condition for pcode {pcode}: {e}")
        return 1.0

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

# --- 4. PLI 계산 핵심 로직 ---
def calculate_single_pli(atbat_data: AtBatData):
    we_end = get_win_expectancy(
        atbat_data.inning, atbat_data.half, atbat_data.outs, atbat_data.runners_code, atbat_data.score_diff
    )
    base_we = we_end if we_end is not None else 0.5
    
    w_env = batting_weather_weight(atbat_data.temp_c)
    w_personal = combine_weights(calculate_condition(atbat_data.batter_id, 2025))
    w_situ = combine_weights(
        streak_weight(atbat_data.loss_streak), pinch_weight(atbat_data.pinch_event),
        ibb_focus_weight(atbat_data.intentional_walk),
        error_momentum_weight(atbat_data.error_happened, atbat_data.next_batter_after_error)
    )
    w_total = combine_weights(w_env, w_personal, w_situ)
    pli_val = round(float(base_we) * w_total, 4)
    return pli_val, base_we, w_total

# --- 5. API 인스턴스 생성 ---
app = FastAPI()

# --- 6. API 엔드포인트 정의 ---
@app.post("/calculate_pli")
async def calculate_pli_endpoint(data: AtBatData):
    pli_val, base_we, w_total = calculate_single_pli(data)
    return {"pli": pli_val, "base_we": base_we, "total_weight": w_total}

# --- 7. 원본 데이터를 처리하는 API 엔드포인트 ---
@app.post("/calculate_pli_raw")
async def calculate_pli_from_raw(raw_data: dict):
    try:
        # 원본 데이터를 가공하는 함수를 호출합니다.
        # 이 함수가 모든 가중치 값을 실제 계산해서 반환할 것입니다.
        processed_data = process_raw_atbat_data(raw_data)
        
        # 가공된 데이터를 AtBatData 모델에 맞게 변환
        atbat_data_model = AtBatData(**processed_data)
        
        # 가공된 데이터를 PLI 계산 함수로 전달
        pli_val, base_we, w_total = calculate_single_pli(atbat_data_model)
        
        return {
            "pli": pli_val,
            "base_we": base_we,
            "total_weight": w_total,
            "message": "PLI calculated successfully from raw data."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- 8. 원본 데이터 가공 함수 (모든 가중치 함수 호출) ---
def process_raw_atbat_data(raw_data: dict) -> dict:
    outs = int(raw_data.get("out", 0))
    score_str = raw_data.get("score", "0:0")
    away_score, home_score = map(int, score_str.split(':'))
    score_diff = home_score - away_score
    on_base = raw_data.get("on_base", {"base1": "0", "base2": "0", "base3": "0"})
    runners_code = on_base["base1"] + on_base["base2"] + on_base["base3"]
    batter_pcode = raw_data.get("actual_batter", {}).get("pcode", None)
    
    # 이제 여기에서 모든 함수를 호출해 실제 값을 가져옵니다.
    stadium_code = raw_data.get("stadium_code")
    loss_streak = raw_data.get("loss_streak") # 임시 기본값
    pinch_event = raw_data.get("pinch_event", False)
    intentional_walk = False # TODO: 원본 데이터에 고의사구 정보가 없으므로 추가 필요
    error_happened = False # TODO: 원본 데이터에 실책 정보가 없으므로 추가 필요
    next_batter_after_error = False # TODO: 원본 데이터에 다음 타자 정보가 없으므로 추가 필요

    # 실제 온도 가져오기
    # API 키는 환경 변수 등 안전한 곳에서 가져와야 합니다.
    weather_temp = get_stadium_temperature(stadium_code, target_hour=datetime.now().hour, auth_key="YOUR_API_KEY")

    return {
        "inning": raw_data.get("inning"),
        "half": raw_data.get("half"),
        "outs": outs,
        "score_diff": score_diff,
        "runners_code": runners_code,
        "batter_id": batter_pcode,
        "stadium_code": stadium_code,
        "temp_c": weather_temp,
        "loss_streak": loss_streak,
        "pinch_event": pinch_event,
        "intentional_walk": intentional_walk,
        "error_happened": error_happened,
        "next_batter_after_error": next_batter_after_error
    }