from kafka import KafkaProducer
import json
import requests
from typing import List, Dict

def produce(topic, result, producer):
    for key, value in result.items():
        print(f"전송 데이터: key = {key}, value = {value}")
        producer.send(topic, key=str(key).encode('utf-8'), value=value)
    
    producer.flush()
    print(f"Kafka에 {len(result)}개의 메시지를 전송했습니다.")

def convert_pitch_result(pitch_result: str) -> str:
    mapping = {"B": "볼", "T": "스트라이크", "F": "파울", "H": "타격"}
    return mapping.get(pitch_result, "기타")

def split_half_inning_relays(relays: List[Dict], inning: int):
    top, bottom, current = [], [], "top"
    for r in relays:
        title = r.get("title", "")
        if f"{inning}회말" in title:
            current = "bottom"
        elif f"{inning}회초" in title:
            current = "top"
        elif current == "top": top.append(r)
        else: bottom.append(r)
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
                    "pitch_result": convert_pitch_result(opt.get("pitchResult", ""))
                })
            if "batterRecord" in opt:
                batter = opt["batterRecord"].get("name")
                bat_order = opt["batterRecord"].get("batOrder")
            result = opt.get("text")
        if batter and result:
            at_bats.append({
                "batter": batter,
                "bat_order": bat_order,
                "result": result,
                "pitch_sequence": pitches
            })
    return at_bats

def crawling(date: str, away: str, home: str) -> Dict:
    result = {}
    for inning in range(1, 12):
        year = date[:4]
        url = f"https://api-gw.sports.naver.com/schedule/games/{date}{away}{home}0{year}/relay?inning={inning}"
        headers = {"User-Agent": "Mozilla/5.0", "Referer": url}
        res = requests.get(url, headers=headers)
        data = res.json()

        try:
            relays = data["result"]["textRelayData"]["textRelays"]
            bot, top = split_half_inning_relays(relays, inning)
            if bot:
                result[f"{inning}회초"] = {
                    "inning": inning, "half": "top", "team": away,
                    "at_bats": extract_at_bats(top)
                }
            if top:
                result[f"{inning}회말"] = {
                    "inning": inning, "half": "bottom", "team": home,
                    "at_bats": extract_at_bats(bot)
                }
        except Exception as e:
            print(f"{inning}회 오류: {e}")
            continue
    return result

def main():
    result = crawling('20250504', 'HH', 'HT')        

    if not result:
        print("크롤링 데이터가 없습니다. Kafka에 전송하지 않습니다.")
        return
    
    else:
        topic = "2025"
        producer = KafkaProducer(
        bootstrap_servers='localhost:9092',
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    produce(topic, result, producer)

if __name__ == "__main__":
    main()