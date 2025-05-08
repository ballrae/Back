import time
import json
import requests
from kafka import KafkaProducer
from typing import List, Dict

def produce(topic, result, producer):
    for key, value in result.items():
        print(f"전송 데이터: key = {key}, value = {value}")
        producer.send(topic, key=str(key).encode('utf-8'), value=value)
    
    producer.flush()
    print(f"✅ Kafka에 {len(result)}개의 메시지를 전송했습니다.")

def convert_pitch_result(pitch_result: str):
    mapping = {
        "B": "볼", "T": "스트라이크", "F": "파울", "S": "헛스윙",
        "H": "타격", "W": "번트 파울"
    }
    if pitch_result is None:
        return None
    return mapping.get(pitch_result, None)  # None이면 포함하지 않음

def split_half_inning_relays(relays: List[Dict], inning: int):
    top, bottom, current = [], [], "top"
    for r in relays:
        title = r.get("title", "")
        if f"{inning}회말" in title:
            current = "bottom"
        elif f"{inning}회초" in title:
            current = "top"
        elif current == "top":
            top.append(r)
        else:
            bottom.append(r)
    return top, bottom

def extract_at_bats(relays: List[Dict]) -> List[Dict]:
    at_bats = []
    for r in reversed(relays):
        options = r.get("textOptions", [])
        batter, bat_order, result, pitches = None, None, None, []
        for opt in options:
            if "pitchNum" in opt:
                pitches.append({
                    "pitch_num": opt["pitchNum"],
                    "pitch_type": opt.get("stuff"),
                    "speed": opt.get("speed"),
                    "count": f"{opt['currentGameState']['ball']}-{opt['currentGameState']['strike']}",
                    "pitch_result": convert_pitch_result(opt.get("pitchResult"))
                })
            if "batterRecord" in opt:
                batter = opt["batterRecord"].get("name")
                bat_order = opt["batterRecord"].get("batOrder")
            if "text" in opt and opt["text"]:
                result = opt["text"]
        
        if batter and (result or len(pitches) > 0):
            at_bats.append({
                "batter": batter,
                "bat_order": bat_order,
                "result": result if result else "(진행 중)",
                "pitch_sequence": pitches
            })

    return at_bats

def crawling(date: str, away: str, home: str, seen: set) -> Dict:
    result = {}
    for inning in range(1, 13):
        year = date[:4]
        url = f"https://api-gw.sports.naver.com/schedule/games/{date}{away}{home}0{year}/relay?inning={inning}"
        headers = {"User-Agent": "Mozilla/5.0", "Referer": url}
        try:
            res = requests.get(url, headers=headers)
            data = res.json()
            relays = data["result"]["textRelayData"]["textRelays"]
            bot, top = split_half_inning_relays(relays, inning)

            if top:
                key = f"{inning}회초"
                if key not in seen:
                    result[key] = {
                        "inning": inning, "half": "top", "team": away,
                        "at_bats": extract_at_bats(top)
                    }
                    seen.add(key)

            if bot:
                key = f"{inning}회말"
                if key not in seen:
                    result[key] = {
                        "inning": inning, "half": "bottom", "team": home,
                        "at_bats": extract_at_bats(bot)
                    }
                    seen.add(key)

        except Exception as e:
            print(f"{inning}회 요청 오류: {e}")
    return result

def main():
    date = '20250507'
    away, home = 'SS', 'HH'
    topic = '2025'
    seen_keys = set()

    producer = KafkaProducer(
        bootstrap_servers='localhost:9092',
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )

    print("📡 실시간 크롤링 시작 (10초 간격)")

    while True:
        new_data = crawling(date, away, home, seen_keys)

        if new_data:
            produce(topic, new_data, producer)
        else:
            print("⏳ 새 데이터 없음")

        time.sleep(10)  # ⏱️ 10초 폴링

if __name__ == "__main__":
    main()