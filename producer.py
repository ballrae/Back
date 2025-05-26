import time
import json
import requests
from kafka import KafkaProducer
from typing import List, Dict
import re
from collections import defaultdict
import sys
from datetime import date

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
def process_pitch_and_events(options: List[Dict]):
    pitch_sequence = []
    result_parts = []
    pitch_num = 0
    ball, strike = 0, 0

    for opt in options:
        text = opt.get("text", "")
        if not text:
            continue

        if "구" in text and any(kw in text for kw in ["볼", "스트라이크", "파울", "헛스윙", "타격"]):
            pitch_num += 1
            pitch_sequence.append({
                "pitch_num": pitch_num,
                "pitch_type": opt.get("stuff"),
                "speed": opt.get("speed"),
                "count": f"{ball}-{strike}",
                "pitch_result": text.replace(f"{pitch_num}구 ", "")
            })
        elif "투수판 이탈" in text:
            pitch_sequence.append({"event": text})
        elif "체크 스윙" in text:
            pitch_sequence.append({"event": text})
        elif ":" in text and "타자" not in text:
            result_parts.append(text)

    return pitch_sequence, "|".join(result_parts)

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

        pitch_sequence, result = process_pitch_and_events(options)

        for opt in options:
            if "batterRecord" in opt:
                actual_batter = opt["batterRecord"].get("name")
                bat_order = opt["batterRecord"].get("batOrder")
            
            if not actual_batter:
                match = re.search(r"\d+번타자\s+(\S+)", text)
                if match:
                    actual_batter = match.group(1)

            text = opt.get("text", "")
            match = re.search(r"(\d+)번타자\s+(\S+)\s+:\s+대타\s+(\S+)", text)
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
                    "appearance_number": 0,
                    "result": text,
                    "pitch_sequence": None
                }
                continue

        if actual_batter:
            if pitch_sequence:
                appearance_counter[(inning, half, actual_batter)] += 1
                appearance_number = appearance_counter[(inning, half, actual_batter)]

                if pending_sub and pending_sub["actual_batter"] == actual_batter:
                    at_bats.append(pending_sub)
                    pending_sub = None

                merge_key = (bat_order, actual_batter, appearance_number)
                if merge_key in pitch_merge_tracker:
                    idx = pitch_merge_tracker[merge_key]
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
        
        # 👇 pitch_sequence가 없어도 appearance_number가 올라가고 result 없이 추가되도록 수정
        elif actual_batter:
            if pending_sub and pending_sub["actual_batter"] == actual_batter:
                at_bats.append(pending_sub)
                pending_sub = None

            merge_key = (bat_order, actual_batter, appearance_number)
            if merge_key not in pitch_merge_tracker:
                at_bats.append({
                    "inning": inning,
                    "half": half,
                    "bat_order": bat_order,
                    "original_batter": None,
                    "actual_batter": actual_batter,
                    "appearance_number": appearance_number,
                    "result": result or "(진행 중)",
                    "pitch_sequence": pitch_sequence or []
                })
                pitch_merge_tracker[merge_key] = len(at_bats) - 1

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

    return result, game_done

def main():
    # today = date.today().strftime("%Y%m%d")
    today = '20250522'
    away, home = 'HH', 'NC'
    dh = 0
    topic = '2025'

    producer = KafkaProducer(
        bootstrap_servers='kafka:9092',
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )

    print("📱 실시간 크롤링 시작 (10초 간격)")
    start_time = time.time()

    while True:
        new_data, game_done = crawling(today, away, home, dh)

        if new_data:
            produce(topic, new_data, producer)
        else:
            print("⏳ 새 데이터 없음")

        if game_done:     
            print("경기 종료됨. 프로그램 종료.")
            sys.exit(0)  # 프로세스 종료

        time.sleep(10)
        if time.time() - start_time >= 4 * 60 * 60:     # 우선 5시간으로 자동화 -> 경기 종료 시그널 들어오면 경기 종료되도록 수정할것
            break

if __name__ == "__main__":
    main()