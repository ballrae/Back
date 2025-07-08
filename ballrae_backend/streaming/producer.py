import time
import json
import requests
from kafka import KafkaProducer
from typing import List, Dict
import re
from collections import defaultdict
import sys
import numpy as np
import argparse

# 이전 데이터 저장용 변수
previous_data = None

# 엔트리 저장 변수
home_entry = None
away_entry = None
home_lineup = None
away_lineup = None

# producer 전송 함수
def produce(topic, result, producer):
    global previous_data

    # 만약 첫 번째 데이터라면, 그 데이터를 전송하고 저장
    if previous_data is None:
        previous_data = result
        for key, value in result.items():
            print(key)
            producer.send(topic, key=str(key).encode('utf-8'), value=value)

        producer.flush()
        print(f"✅ 최초 데이터 전송")
        return

    # 변경된 부분만 추출하는 로직
    changed_data = {}
    for key, value in result.items():
        # 이전 데이터와 비교하여 값이 다르면 변경된 데이터로 간주
        if key not in previous_data or previous_data[key] != value:
            changed_data[key] = value

    # 변경된 부분만 있을 경우에만 전송
    if changed_data:
        print(f"✅ 변경된 데이터 전송:")
        for key, value in changed_data.items():
            producer.send(topic, key=str(key).encode('utf-8'), value=value)
        producer.flush()

        # 이전 데이터를 업데이트
        previous_data = result

    else:
        print("- 변경된 데이터 없음")

# pitch result -> 이니셜을 문자 형태로 변환
def convert_pitch_result(pitch_result: str):
    mapping = {
        "B": "볼", "T": "스트라이크", "F": "파울", "S": "헛스윙",
        "H": "타격", "W": "번트 파울"
    }

    print(pitch_result)

    if pitch_result is None:
        return None
    return mapping.get(pitch_result, None) 

# y = 0 (홈플레이트)에 도달하는 시간 t 계산
def compute_plate_coordinates(pitch):
    try:            
        if pitch is not None:
            y0, vy0, ay = pitch["y0"], pitch["vy0"], pitch["ay"]
            a = 0.5 * ay
            b = vy0
            c = y0
            t = (-b - np.sqrt(b**2 - 4*a*c)) / (2*a)
            x = pitch["x0"] + pitch["vx0"] * t + 0.5 * pitch["ax"] * t**2
            z = pitch["z0"] + pitch["vz0"] * t + 0.5 * pitch["az"] * t**2
            return float(x), float(z)
        else:
            return None
    except:
        return None

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
            current = "bot"
            continue
        elif f"{inning}회초" in title:
            current = "top"
            continue

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

    temp_pitch_sequence = {}
    event = []

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
        
        if "구" in text and any(kw in text for kw in ["볼", "스트라이크", "파울", "헛스윙", "타격"]) and not any(kw in text for kw in ["아웃", "안타", '2루타', '3루타', '홈런']):
            pitch_num += 1

            temp_pitch_sequence["pitch_num"] = pitch_num
            temp_pitch_sequence['pitch_type'] = opt.get('stuff')
            temp_pitch_sequence['pitch_coordinate'] = points
            temp_pitch_sequence['speed'] = opt.get('speed')
            temp_pitch_sequence['count'] = f"{ball}-{strike}"
            temp_pitch_sequence['pitch_result'] = text.replace(f"{pitch_num}구 ", "")
            if event:
                temp_pitch_sequence['event'] = "|".join(event)
            else:
                temp_pitch_sequence['event'] = None  # 기본값은 None으로 설정

            pitch_sequence.append(temp_pitch_sequence)

            temp_pitch_sequence = {}
            event = []

        elif any(keyword in text for keyword in ["투수판 이탈", "체크 스윙", "도루", "비디오 판독", "교체"]):
            event.append(text)
            continue

        elif ":" in text and "타자" not in text:
            result_parts.append(text)

        if temp_strike_zone is not None and strike_zone is None:
            strike_zone = temp_strike_zone
        
    if event!=[]:
        pitch_sequence.append({
            "pitch_num": pitch_num+1,
            "event": event
        })

    return pitch_sequence, "|".join(result_parts), strike_zone

# 타석 정보
def extract_at_bats(relays: List[Dict], inning: int, half: str, entries: List) -> List[Dict]:
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
            text = result or ""

            pitcher = opt['currentGameState']['pitcher']
            pitcher = find_name_by_pcode(entries, pitcher)
            
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
                    "pitcher": pitcher,
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
                    text += f"|{result}"
            else:
                at_bats.append({
                    "inning": inning,
                    "half": half,
                    "pitcher": None,                    
                    "bat_order": bat_order,
                    "original_batter": None,
                    "actual_batter": actual_batter,
                    "appearance_number": appearance_number,
                    "strike_zone": strike_zone,
                    "full_result": result or "(진행 중)",
                    "pitch_sequence": pitch_sequence
                })
                pitch_merge_tracker[merge_key] = len(at_bats) - 1
                current_at_bat_key = merge_key

        elif current_at_bat_key and result:
            prev_bat_order = current_at_bat_key[0]
            if bat_order == prev_bat_order:
                idx = pitch_merge_tracker[current_at_bat_key]
                text += f"|{result}"

        if text.startswith(actual_batter):
            split_parts = text.split("|")
            main_play = split_parts[0].split(":", 1)[1].strip()

            idx = pitch_merge_tracker[current_at_bat_key]
            at_bats[idx]["main_result"] = main_play

            full_extras = split_parts[1:]  # 첫 항목 제외
            if full_extras:
                at_bats[idx]["full_result"] = "|".join(full_extras).strip()

    return at_bats

# pcode를 통해 name을 찾는 함수
def find_name_by_pcode(entries, pcode):
    # 배터 리스트와 투수 리스트에서 pcode를 찾기
    for entry in entries:
        for group in [entry['batter'], entry['pitcher']]:
            for player in group:
                if player['pcode'] == str(pcode):
                    return player['name']
                else:
                    continue
    return None

# 크롤링 함수
def crawling(game):
    global home_entry
    global away_entry
    global home_lineup
    global away_lineup
    global game_done

    result = {}
    game_done = False
    # result['game_over'] = game_done

    away = game[8:10]
    home = game[10:12]

    result['game_id'] = game

    for inning in range(1, 12):
        url = f"https://api-gw.sports.naver.com/schedule/games/{game}/relay?inning={inning}"
        headers = {"User-Agent": "Mozilla/5.0", "Referer": url}
        try:
            res = requests.get(url, headers=headers)
            data = res.json()
            
            relays = data["result"]["textRelayData"]["textRelays"]
            top, bot, game_done = split_half_inning_relays(relays, inning)

            home_entry = data["result"]["textRelayData"]['homeEntry']
            away_entry = data["result"]["textRelayData"]['awayEntry']
            home_lineup = data["result"]["textRelayData"]['homeLineup']
            away_lineup = data["result"]["textRelayData"]['awayLineup']

            entries = [home_entry, away_entry, home_lineup, away_lineup]
        
            if top:
                key = f"{inning}회초"
                result[key] = {
                    "game_id": game,
                    "inning": inning, "half": "top", "team": away,
                    "at_bats": extract_at_bats(top, inning, "top", entries)
                }

            if bot:
                key = f"{inning}회말"
                result[key] = {
                    "game_id": game,
                    "inning": inning, "half": "bot", "team": home,
                    "at_bats": extract_at_bats(bot, inning, "bot", entries)
                }
            
            if game_done == True:
                result['game_over'] = game_done
                return result, game_done
            
        except Exception as e:
            print(f"{inning}회 요청 오류: {e}")
            continue

    return result, game_done

def main():
    # parser = argparse.ArgumentParser()
    # parser.add_argument('--id')
    # args = parser.parse_args()

    game = "20250706HHWO02025"

    topic = '2025'

    producer = KafkaProducer(
        bootstrap_servers='kafka:9092',
        # bootstrap_servers='localhost:9092',
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )

    print("- 실시간 크롤링 시작 (10초 간격)")

    while True:
        new_data, game_done = crawling(game)

        if new_data:
            produce(topic, new_data, producer)
        else:
            print("- 새 데이터 없음")

        if game_done:     
            print("경기 종료됨. 프로그램 종료.")
            sys.exit(0)  # 프로세스 종료

        time.sleep(20)

if __name__ == "__main__":
    main()