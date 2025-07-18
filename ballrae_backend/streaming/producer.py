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
import os
import datetime
import sys
import concurrent.futures
import threading

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ballrae_backend.settings")

import django
django.setup()

from ballrae_backend.games import models
from ballrae_backend.games.services import save_at_bat_transactionally

# 엔트리 저장 변수
home_entry = None
away_entry = None
home_lineup = None
away_lineup = None

TEAM_MAP = {
    'KA': 'HT',
    'HE': 'WO',
    'SL': 'SK',
    'DS': 'OB',
    'HT': 'KA',
    'WO': 'HE',
    'SK': 'SL',
    'OB': 'DS'
}

def team_map(team):
    return TEAM_MAP.get(team, team)

# producer 전송 함수
def produce(topic, result, producer, previous_data):
    # 만약 첫 번째 데이터라면, 그 데이터를 전송하고 저장
    if previous_data is None:
        previous_data = result
        for key, value in result.items():
            print(key)
            producer.send(topic, key=str(key).encode('utf-8'), value=value)

        producer.flush()
        return previous_data

    # 변경된 부분만 추출하는 로직
    changed_data = {}
    for key, value in result.items():
        # 이전 데이터와 비교하여 값이 다르면 변경된 데이터로 간주
        if key not in previous_data or previous_data[key] != value:
            changed_data[key] = value

    # 변경된 부분만 있을 경우에만 전송
    if changed_data:
        print(f"변경된 데이터 전송:")
        for key, value in changed_data.items():
            producer.send(topic, key=str(key).encode('utf-8'), value=value)
        producer.flush()

        # 이전 데이터를 업데이트
        previous_data = result

    else:
        print("- 변경된 데이터 없음")
        
    return previous_data

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
            pitch_id = opt.get('ptsPitchId', [])
            if pitch_id and pitch_id != '-1':
                pitch_pts = next((p for p in pitch_options if p["pitchId"] == pitch_id), None)
                points = [compute_plate_coordinates(pitch_pts)]
                
                strike_zone_left = -0.75
                strike_zone_right = 0.75
                strike_zone_top = pitch_pts.get('topSz', 3.50725)
                strike_zone_bottom = pitch_pts.get('bottomSz', 1.60515)
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

def extract_at_bats(relays: List[Dict], inning: int, half: str, merged_dict: Dict) -> List[Dict]:
    at_bats = []
    pitch_merge_tracker = dict()
    appearance_counter = defaultdict(int)
    pending_sub = None
    current_at_bat_key = None

    for r in relays:
        options = r.get("textOptions", [])
        pitch_sequence, result, strike_zone = process_pitch_and_events(r)
        actual_batter, original_batter, bat_order, pitcher = None, None, None, None
        out, score = None, None
        base1, base2, base3 = None, None, None

        for opt in options:
            text = opt.get("text", "")
            game_state = opt.get('currentGameState', {})

            pcode = game_state.get('pitcher')
            pitcher = merged_dict.get(pcode, None)
            score = f"{game_state.get('awayScore')}:{game_state.get('homeScore')}"
            base1, base2, base3 = game_state.get('base1'), game_state.get('base2'), game_state.get('base3')
            out = game_state.get('out')

            # 타자 정보 파싱
            batter_info = opt.get("batterRecord", {})
            actual_batter = batter_info.get("name", actual_batter)
            bat_order = batter_info.get("batOrder", bat_order)

            # 교체 상황 파싱
            match = re.search(r"(\d+)번타자\s+(\S+)\s+:\s+대타\s+(\S+)", text)
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
                    "out": out,
                    "score": score,
                    "on_base": None,
                    "strike_zone": None,
                    "appearance_number": 0,
                    "result": text,
                    "pitch_sequence": None
                }

        # appearance number 계산
        merge_key = (inning, half, bat_order, actual_batter)
        appearance_counter[merge_key] += 1
        appearance_number = appearance_counter[merge_key]
        pitch_merge_key = (bat_order, actual_batter, appearance_number)

        # pending_sub 처리
        if pending_sub and pending_sub["actual_batter"] == actual_batter:
            pending_sub["appearance_number"] = appearance_number
            at_bats.append(pending_sub)
            pitch_merge_tracker[pitch_merge_key] = len(at_bats) - 1
            pending_sub = None

        # 타석 병합 또는 새 타석 생성
        if pitch_merge_key in pitch_merge_tracker:
            idx = pitch_merge_tracker[pitch_merge_key]
            if at_bats[idx].get("pitch_sequence"):
                at_bats[idx]["pitch_sequence"].extend(pitch_sequence)
            else:
                at_bats[idx]["pitch_sequence"] = pitch_sequence
            if result:
                at_bats[idx]["full_result"] = (at_bats[idx].get("full_result", "") + f"|{result}").strip("|")
        else:
            new_atbat = {
                "inning": inning,
                "half": half,
                "pitcher": pitcher,
                "bat_order": bat_order,
                "original_batter": None,
                "actual_batter": actual_batter,
                "out": out,
                "score": score,
                "on_base": {
                    "base1": base1,
                    "base2": base2,
                    "base3": base3
                },
                "appearance_number": appearance_number,
                "strike_zone": strike_zone,
                "full_result": result or "(진행 중)",
                "pitch_sequence": pitch_sequence
            }
            at_bats.append(new_atbat)
            pitch_merge_tracker[pitch_merge_key] = len(at_bats) - 1
            current_at_bat_key = pitch_merge_key

        # main_result 추출
        if result and actual_batter and result.startswith(actual_batter):
            split_parts = result.split("|")
            main_play = ""
            if split_parts:
                for s in split_parts:
                    if s.startswith(actual_batter): main_play = s.split(': ')[1]
            idx = pitch_merge_tracker[pitch_merge_key]
            at_bats[idx]["main_result"] = main_play
            if len(split_parts) > 1:
                at_bats[idx]["full_result"] = "|".join(split_parts[1:]).strip()

    return at_bats

def create_merged_dict(entries):
    merged = {}
    for entry_list in entries:
        pitchers = entry_list['pitcher']
        for pitcher in pitchers:
            pcode = pitcher.get("pcode")
            if pcode is not None:
                merged[pcode] = pitcher['name']
            else: continue
    return merged

def get_lineup(lineup):
    result = {}
    for b in lineup['batter']:
        result['batter'] = {'position': b['posName'], 'name': b['name']}
    
    for p in lineup['pitcher']:
        result['pitcher'] = {'position': 'pitcher', 'name': p['name']}

    return result


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

    away = team_map(game[8:10])
    home = team_map(game[10:12])

    game_id = f'{game[:8]}{away}{home}{game[12:]}'

    result['game_id'] = game_id

    merged_entries = {}

    for inning in range(1, 12):
        url = f"https://api-gw.sports.naver.com/schedule/games/{game}/relay?inning={inning}"
        headers = {"User-Agent": "Mozilla/5.0", "Referer": url}
        try:
            res = requests.get(url, headers=headers)
            data = res.json()
            
            if "result" not in data or "textRelayData" not in data["result"]:
                raise KeyError("'result' or 'textRelayData' not found")
        
            relays = data["result"]["textRelayData"]["textRelays"]
            top, bot, game_done = split_half_inning_relays(relays, inning)
            home_lineup = data["result"]["textRelayData"]['homeLineup']
            away_lineup = data["result"]["textRelayData"]['awayLineup']
            
            result['home_lineup'] = get_lineup(home_lineup)
            result['away_lineup'] = get_lineup(away_lineup)
            
            if inning == 1:
                home_entry = data["result"]["textRelayData"]['homeEntry']
                away_entry = data["result"]["textRelayData"]['awayEntry']

                entries = [home_entry, away_entry, home_lineup, away_lineup]

                merged_entries = create_merged_dict(entries)
        
            if top:
                key = f"{inning}회초"
                result[key] = {
                    "game_id": game_id,
                    "inning": inning, "half": "top", "team": away,
                    "at_bats": extract_at_bats(top, inning, "top", merged_entries)
                }

            if bot:
                key = f"{inning}회말"
                result[key] = {
                    "game_id": game_id,
                    "inning": inning, "half": "bot", "team": home,
                    "at_bats": extract_at_bats(bot, inning, "bot", merged_entries)
                }
            
            if game_done == True:
                result['game_over'] = game_done
                return result, game_done

        except KeyError as e:
            print("경기 시작 전")
            break    
        
        except Exception as e:
            print(f"{game} {inning}회 요청 오류: {e}")
            continue

    return result, game_done

def crawl_game_loop(game_id, topic, producer):
    previous_data = None
    print(f"[{game_id}] 실시간 크롤링 시작")

    while True:
        try:
            result, game_done = crawling(game_id)

            if result:
                previous_data = produce(topic, result, producer, previous_data)
            else:
                print(f"[{game_id}] 새 데이터 없음")

            if game_done:
                print(f"[{game_id}] 경기 종료. 스레드 종료")
                break

        except KeyError as e:
            print(f"[{game_id}] KeyError 발생: {e}. 크롤링 종료")
            break

        except Exception as e:
            print(f"[{game_id}] 오류 발생: {e}")
        
        time.sleep(20)

def get_realtime_data():
    # parser = argparse.ArgumentParser()
    # parser.add_argument('--id')
    # args = parser.parse_args()

    today = datetime.date.today()
    game_ids = models.Game.objects.filter(date__date=today).values_list('id', flat=True)
    new_game_id = []

    for game in game_ids:
            date = game[:8]
            away_team = team_map(game[8:10])
            home_team = team_map(game[10:12])

            dh = game[12]
            year = game[:4]

            game_id = f"{date}{away_team}{home_team}{dh}{year}"
            new_game_id.append(game_id)

    topic = '2025'

    producer = KafkaProducer(
        bootstrap_servers='kafka:9092',
        # bootstrap_servers='localhost:9092',
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(crawl_game_loop, game_id, topic, producer) for game_id in new_game_id]

        # 모든 스레드가 끝날 때까지 대기
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"스레드 내부 에러: {e}")
    

def get_all_game_datas(select_year):
    game_ids = models.Game.objects.filter(
        status='done',
        # date__date__gt=datetime.datetime(2025, 6, 28).date(),
        id__startswith=str(select_year)
    ).values_list('id', flat=True)
    
    for game in game_ids:
        date = game[:8]
        away_team = team_map(game[8:10])
        home_team = team_map(game[10:12])

        dh = game[12]
        year = game[:4]

        game_id = f"{date}{away_team}{home_team}{dh}{year}"
        print(game_id)

        new_data, game_done = crawling(game_id)
        # topic = year
        # producer = KafkaProducer(
        #     bootstrap_servers='kafka:9092',
        #     # bootstrap_servers='localhost:9092',
        #     value_serializer=lambda v: json.dumps(v).encode('utf-8')
        # )

        if new_data:
            for key in new_data.keys():
                if key in ['game_over', 'home_lineup', 'away_lineup', 'game_id']: continue
                else:
                    # print([key])
                    save_at_bat_transactionally(new_data[key], game)
        else:
            print("- 새 데이터 없음")

        if game_done: continue

        

def test():
    new_data, game_done = crawling('20230316SKLT02023')

    if new_data:
        for key in new_data.keys():
            if key == 'game_id' or key == 'game_over': continue
            else: print(new_data[key]['game_id'])
                
    # topic = '2025'
    # producer = KafkaProducer(
    #     bootstrap_servers='kafka:9092',
    #     # bootstrap_servers='localhost:9092',
    #     value_serializer=lambda v: json.dumps(v).encode('utf-8')
    # )
    
    # if new_data:
    #     produce(topic, new_data, producer, None)
    # else:
    #     print("- 새 데이터 없음")
    
    if game_done: sys.exit(0)

def main():
    # test()
    # get_realtime_data()
    # get_all_game_datas(2023)
    get_all_game_datas(2024)
    # get_all_game_datas(2025)
    # print(team_map('HE'))

if __name__ == "__main__":
    main()