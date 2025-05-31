import time
import json
import requests
from kafka import KafkaProducer
from typing import List, Dict
import re
from collections import defaultdict
import sys
from datetime import date
import numpy as np

# producer 전송 함수
def produce(topic, result, producer):
    for key, value in result.items():
        # print(f"전송 데이터: key = {key}, value = {value}")
        producer.send(topic, key=str(key).encode('utf-8'), value=value)

    producer.flush()
    print(f"✅ Kafka에 {len(result)}개의 메시지를 전송했습니다.")

# pitch result -> 이니셜을 문자 형태로 변환
def convert_pitch_result(pitch_result: str):
    mapping = {
        "B": "볼", "T": "스트라이크", "F": "파울", "S": "헛스윙",
        "H": "타격", "W": "번트 파울"
    }
    if pitch_result is None:
        return None
    return mapping.get(pitch_result, None) 

# y = 0 (홈플레이트)에 도달하는 시간 t 계산
def compute_plate_coordinates(pitch):
    y0, vy0, ay = pitch["y0"], pitch["vy0"], pitch["ay"]
    a = 0.5 * ay
    b = vy0
    c = y0
    t = (-b - np.sqrt(b**2 - 4*a*c)) / (2*a)
    x = pitch["x0"] + pitch["vx0"] * t + 0.5 * pitch["ax"] * t**2
    z = pitch["z0"] + pitch["vz0"] * t + 0.5 * pitch["az"] * t**2
    return float(x), float(z)

# 초/말 공격 나눔
def split_half_inning_relays(relays: List[Dict], inning: int):
    top, bottom, current = [], [], "top"
    game_over_trigger = False

    for r in reversed(relays):
        title = r.get("title", "")
        if "====" in title:
            game_over_trigger = True
            continue  # 이 텍스트 자체는 저장 안 함

        if f"{inning}회말" in title:
            current = "bottom"
        elif f"{inning}회초" in title:
            current = "top"

        if current == "top":
            top.append(r)
        else:
            bottom.append(r)

    return top, bottom, game_over_trigger

# pitch sequence와 주자 결과 등 텍스트를 처리하는 함수
def process_pitch_and_events(relay):
    pitch_sequence = []
    result_parts = []
    pitch_num = 0
    ball, strike = 0, 0
    strike_zone = None


    options = relay.get("textOptions", [])
    pitch_options = relay.get('ptsOptions')

    for opt in options:
        text = opt.get("text", "")
        if not text:
            continue
        ball = opt['currentGameState']['ball']
        strike = opt['currentGameState']['strike']

        pitch_id = None
        points = None
        temp_strike_zone = None
        
        if pitch_options:
            pitch_id = opt.get('ptsPitchId')
            if pitch_id:
                pitch_pts = next((p for p in pitch_options if p["pitchId"] == pitch_id), None)
                points = [compute_plate_coordinates(pitch_pts)]
                
                strike_zone_left = -0.75
                strike_zone_right = 0.75
                strike_zone_top = pitch_pts['topSz']
                strike_zone_bottom = pitch_pts['bottomSz']
                temp_strike_zone = [strike_zone_top, strike_zone_bottom, strike_zone_right, strike_zone_left]
        
        if "구" in text and any(kw in text for kw in ["볼", "스트라이크", "파울", "헛스윙", "타격"]):
            pitch_num += 1
            pitch_sequence.append({
                "pitch_num": pitch_num,
                "pitch_type": opt.get("stuff"),
                "pitch_coordinate": points,
                "speed": opt.get("speed"),
                "count": f"{ball}-{strike}",
                "pitch_result": text.replace(f"{pitch_num}구 ", ""),
                "event": None
            })
        elif "투수판 이탈" in text:
            pitch_sequence.append({
                "pitch_num": pitch_num,
                "pitch_type": None,
                "pitch_coordinate": None,
                "speed": None,
                "count": None,
                "pitch_result": None,
                "event": text
            })
        elif "체크 스윙" in text:
            pitch_sequence.append({
                "pitch_num": pitch_num,
                "pitch_type": None,
                "pitch_coordinate": None,
                "speed": None,
                "count": None,
                "pitch_result": None,
                "event": text
            })
        elif ":" in text and "타자" not in text:
            result_parts.append(text)

        if temp_strike_zone is not None and strike_zone is None:
            strike_zone = temp_strike_zone

    return pitch_sequence, "|".join(result_parts), strike_zone

# 타석 정보
def extract_at_bats(relays: List[Dict], inning: int, half: str) -> List[Dict]:
    at_bats = []
    pitch_merge_tracker = dict()
    appearance_counter = defaultdict(int)
    pending_sub = None
    current_at_bat_key = None

    for r in relays:
        options = r.get("textOptions", [])
        result = None
        actual_batter, original_batter = None, None
        bat_order = None

        pitch_sequence, result, strike_zone = process_pitch_and_events(r)

        for opt in options:
            if "batterRecord" in opt:
                actual_batter = opt["batterRecord"].get("name")
                bat_order = opt["batterRecord"].get("batOrder")
                
            if not actual_batter:
                match = re.search(r"\d+번타자\s+(\S+)", opt.get("text", ""))
                if match:
                    actual_batter = match.group(1)

            match = re.search(r"(\d+)번타자\s+(\S+)\s+:\s+대타\s+(\S+)", opt.get("text", ""))
            if match:
                bat_order = int(match.group(1))
                original_batter = match.group(2)
                actual_batter = match.group(3)
            
                pending_sub = {
                    "inning": inning,
                    "half": half,
                    "bat_order": bat_order,
                    "original_batter": original_batter,
                    "actual_batter": actual_batter,
                    "strike_zone": None,
                    "appearance_number": 0,
                    "result": opt.get("text", ""),
                    "pitch_sequence": None
                }

        if actual_batter:
            appearance_counter[(inning, half, actual_batter)] += 1
            appearance_number = appearance_counter[(inning, half, actual_batter)]

            if pending_sub and pending_sub["actual_batter"] == actual_batter:
                at_bats.append(pending_sub)
                pending_sub = None

            merge_key = (bat_order, actual_batter, appearance_number)
            if merge_key in pitch_merge_tracker:
                idx = pitch_merge_tracker[merge_key]
                if not at_bats[idx].get("pitch_sequence"):
                    at_bats[idx]["pitch_sequence"] = pitch_sequence
                else:
                    at_bats[idx]["pitch_sequence"].extend(pitch_sequence)
                if result:
                    at_bats[idx]["result"] += f"|{result}"
            else:
                at_bats.append({
                    "inning": inning,
                    "half": half,
                    "bat_order": bat_order,
                    "original_batter": None,
                    "actual_batter": actual_batter,
                    "appearance_number": appearance_number,
                    "strike_zone": strike_zone,
                    "result": result or "(진행 중)",
                    "pitch_sequence": pitch_sequence
                })
                pitch_merge_tracker[merge_key] = len(at_bats) - 1
                current_at_bat_key = merge_key

        elif current_at_bat_key and result:
            prev_bat_order = current_at_bat_key[0]
            if bat_order == prev_bat_order:
                idx = pitch_merge_tracker[current_at_bat_key]
                at_bats[idx]["result"] += f"|{result}"

    return at_bats

# 크롤링 함수
def crawling(date: str, away: str, home: str, dh):
    result = {}
    result['game_over'] = False

    for inning in range(1, 12):
        year = date[:4]
        url = f"https://api-gw.sports.naver.com/schedule/games/{date}{away}{home}{dh}{year}/relay?inning={inning}"
        headers = {"User-Agent": "Mozilla/5.0", "Referer": url}
        try:
            res = requests.get(url, headers=headers)
            data = res.json()
            relays = data["result"]["textRelayData"]["textRelays"]
            top, bot, game_done = split_half_inning_relays(relays, inning)

            if top:
                key = f"{inning}회초"
                result[key] = {
                    "inning": inning, "half": "top", "team": away,
                    "at_bats": extract_at_bats(top, inning, "top")
                }

            if bot:
                key = f"{inning}회말"
                result[key] = {
                    "inning": inning, "half": "bottom", "team": home,
                    "at_bats": extract_at_bats(bot, inning, "bottom")
                }

            result['game_over'] = game_done
            
            if game_done:
                return result, game_done
            
        except Exception as e:
            print(f"{inning}회 요청 오류: {e}")

        print(result)

    return result, game_done

def main():
    # today = date.today().strftime("%Y%m%d")
    today = '20250522'
    away, home = 'HH', 'NC'
    dh = 0
    topic = '2025'

    producer = KafkaProducer(
        bootstrap_servers='kafka:9092',
        # bootstrap_servers='localhost:9092',
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )

    print("- 실시간 크롤링 시작 (10초 간격)")
    start_time = time.time()

    while True:
        new_data, game_done = crawling(today, away, home, dh)

        if new_data:
            produce(topic, new_data, producer)
        else:
            print("- 새 데이터 없음")

        if game_done:     
            print("경기 종료됨. 프로그램 종료.")
            sys.exit(0)  # 프로세스 종료

        time.sleep(10)
        if time.time() - start_time >= 4 * 60 * 60:     # 우선 5시간으로 자동화 -> 경기 종료 시그널 들어오면 경기 종료되도록 수정할것
            break

if __name__ == "__main__":
    main()