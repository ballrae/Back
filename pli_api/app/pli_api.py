import pandas as pd
from flask import Flask, request, jsonify

# --- 1. 데이터 로딩 (서버 시작 시 한 번만 실행) ---
try:
    wpa_data = pd.read_csv('data/kbo_we_matrix_filtered.csv')
    WE_MAP = {}
    for _, row in wpa_data.iterrows():
        # 상황을 나타내는 고유한 튜플을 Key로, win_expectancy를 Value로 사용
        key = (
            row['inning_number'],
            row['half'] == 'bot',  # 'top'/'bot' 대신 True/False 사용
            row['out'],
            row['runner_on_1b'],
            row['runner_on_2b'],
            row['runner_on_3b'],
            row['score_diff']
        )
        WE_MAP[key] = row['win_expectancy']
except FileNotFoundError:
    print("Warning: kbo_we_matrix_filtered.csv not found. WE-based PLI will use default values.")
    WE_MAP = {}

# --- 2. PLI 계산에 필요한 보조 함수들 ---
# 이 함수들은 기존에 개발했던 로직을 옮겨온 것으로 가정합니다.
# 실제 DB 연동이나 복잡한 로직은 여기에 구현해야 합니다.

def get_win_expectancy(inning, half, outs, runners_code, score_diff):
    is_home = (half == 'bot')
    runners = [int(r) for r in runners_code]
    key = (inning, is_home, outs, runners[0], runners[1], runners[2], score_diff)
    return WE_MAP.get(key, None)

def combine_weights(*weights):
    """모든 가중치를 곱하여 합산 가중치를 반환합니다."""
    total_weight = 1.0
    for w in weights:
        if w is not None:
            total_weight *= w
    return total_weight

def calculate_situation_level(inning, outs, runners_code, score_diff):
    # 기존 코드의 calculate_situation_level 함수 로직을 그대로 사용
    return (1, "일상적 교체", 0) # 더미 값

def batting_weather_weight(temp_c):
    # 기존 코드의 batting_weather_weight 함수 로직을 그대로 사용
    return 1.0 # 더미 값

def calculate_condition(pcode, season):
    # 기존 코드의 calculate_condition 함수 로직을 그대로 사용
    return 1.0 # 더미 값

def streak_weight(loss_streak):
    # 기존 코드의 streak_weight 함수 로직을 그대로 사용
    return 1.0 # 더미 값

def pinch_weight(is_pinch_hitter):
    return 1.5 if is_pinch_hitter else 1.0

def ibb_focus_weight(is_ibb):
    return 2.0 if is_ibb else 1.0

def error_momentum_weight(is_error, is_next_batter):
    if is_error and is_next_batter:
        return 1.2
    return 1.0

# --- 3. PLI 계산 핵심 로직 ---
# 단일 타석에 대한 PLI를 계산합니다.
def calculate_single_pli(atbat_data: dict):
    # 1. 타석 종료 시점의 WE 값 가져오기
    we_end = get_win_expectancy(
        atbat_data.get('inning'),
        atbat_data.get('half'),
        atbat_data.get('outs'),
        atbat_data.get('runners_code'),
        atbat_data.get('score_diff')
    )
    
    # WE 데이터가 없으면 0.5를 기본값으로 사용
    base_we = we_end if we_end is not None else 0.5

    # 2. 모든 가중치 요소 계산
    w_env = batting_weather_weight(atbat_data.get("temp_c"))
    w_personal = combine_weights(calculate_condition(atbat_data.get('batter_id'), 2025))
    w_situ = combine_weights(
        streak_weight(atbat_data.get("loss_streak")),
        pinch_weight(bool(atbat_data.get("pinch_event"))),
        ibb_focus_weight(bool(atbat_data.get("intentional_walk"))),
        error_momentum_weight(bool(atbat_data.get("error_happened")), bool(atbat_data.get("next_batter_after_error")))
    )
    w_total = combine_weights(w_env, w_personal, w_situ)
    
    # 3. 최종 PLI 값 계산 (WE 값에 가중치를 곱함)
    pli_val = round(float(base_we) * w_total, 4)
    
    return pli_val, base_we, w_total

# --- 4. API 엔드포인트 정의 ---
app = Flask(__name__)

@app.route('/calculate_pli', methods=['POST'])
def calculate_pli_endpoint():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No input data provided."}), 400
        
        pli_val, base_we, w_total = calculate_single_pli(data)
        
        return jsonify({
            "pli": pli_val,
            "base_we": base_we,
            "total_weight": w_total,
            "message": "PLI calculated successfully."
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Docker 컨테이너에서 외부 접근을 허용하려면 host='0.0.0.0'으로 설정해야 합니다.
    app.run(host='0.0.0.0', port=8002)