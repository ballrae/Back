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
import sys
import concurrent.futures
import threading
import datetime
from django.db.models import Q

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ballrae_backend.settings")

import django
django.setup()

from ballrae_backend.games import models
from ballrae_backend.games.services import save_at_bat_transactionally
from ballrae_backend.streaming.redis_client import redis_client

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

def mark_game_status(game_id: str, status):
    try:
        updated = models.Game.objects.filter(id=game_id).update(status=status)

    except Exception as e:
        print(f"경기 상태 마킹 실패: {status}, {type(e).__name__}: {e}")

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

# 실시간 수비위치 저장 함수
def build_defense_positions_payload(game_id: str, home_team: str, away_team: str,
                                    home_lineup: dict, away_lineup: dict):
    def to_dh10(pos):
        if pos is None:
            return None
        s = str(pos).strip()
        if s.isdigit():
            return s
        if s in ("지명타자", "DH", "지타"):
            return "10"
        return s

    def get_pcode(obj):
        return str(obj.get("pcode") or obj.get("pCode") or obj.get("id") or "").strip()

    def extract(lineup):
        items = []

        # 타자들: 지명타자는 10으로 매핑
        for b in (lineup.get("batter") or []):
            pcode = get_pcode(b)
            pos = b.get("pos") or b.get("posName")
            pos_code = to_dh10(pos)
            if pcode and pos_code:
                items.append({"pcode": pcode, "pos": pos_code})

        # 투수(선발 포함): 무조건 1로
        for p in (lineup.get("pitcher") or []):
            pcode = get_pcode(p)
            if pcode:
                items.append({"pcode": pcode, "pos": "1"})

        return items

    return {
        "game_id": game_id,
        "home_team": home_team,
        "away_team": away_team,
        "home": extract(home_lineup),
        "away": extract(away_lineup),
    }

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

            pitcher = game_state.get('pitcher')
            actual_batter = game_state.get('batter')
            score = f"{game_state.get('awayScore')}:{game_state.get('homeScore')}"
            base1, base2, base3 = game_state.get('base1'), game_state.get('base2'), game_state.get('base3')
            out = game_state.get('out')

            # 타자 정보 파싱
            batter_info = opt.get("batterRecord", {})
            # actual_batter = batter_info.get("name", actual_batter)
            # actual_batter = batter_info.get("name", actual_batter)
            # original_batter = merged_dict.get(original_batter, '')
            # actual_batter = merged_dict.get(actual_batter)
            bat_order = batter_info.get("batOrder", bat_order)

            # 교체 상황 파싱
            match = re.search(r"(\d+)번타자\s+(\S+)\s+:\s+대타\s+(\S+)", text)
            if match:
                bat_order = int(match.group(1))
                original_batter = merged_dict.get(match.group(2), '')
                actual_batter = merged_dict.get(match.group(3), '')
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
                    "full_result": text,
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
        actual_batter_name = merged_dict[actual_batter]
        if result and actual_batter_name and result.startswith(actual_batter_name):
            split_parts = result.split("|")
            main_play = ""
            if split_parts:
                for s in split_parts:
                    if s.startswith(actual_batter_name): main_play = s.split(': ')[1]
            idx = pitch_merge_tracker[pitch_merge_key]
            at_bats[idx]["main_result"] = main_play
            if len(split_parts) > 1:
                at_bats[idx]["full_result"] = "|".join(split_parts[1:]).strip()

    return at_bats

def create_merged_dict(entries, game_id):
    merged = {}
    existing_pcodes = set(models.Player.objects.values_list('pcode', flat=True))

    # game_id에서 팀 코드 추출
    away_code = team_map(game_id[8:10])
    home_code = team_map(game_id[10:12])

    for entry_list in entries:
        # 엔트리 팀 판단
        is_home = entry_list == home_entry or entry_list == home_lineup
        team_id = home_code if is_home else away_code

        for group in ['pitcher', 'batter']:
            for player in entry_list[group]:
                pcode = player.get("pcode")
                name = player.get("name")
                position = "B" if group == "batter" else "P"

                if pcode is None or name is None:
                    continue

                if pcode not in existing_pcodes:
                    models.Player.objects.create(
                        pcode=pcode,
                        player_name=name,
                        team_id=team_id,
                        position=position
                    )
                    existing_pcodes.add(pcode)

                merged[pcode] = name

    return merged

def get_lineup(lineup):
    result = {}
    for b in lineup['batter']:
        result['batter'] = {'position': b['posName'], 'name': b['name']}
    
    for p in lineup['pitcher']:
        result['pitcher'] = {'position': 'pitcher', 'name': p['name']}

    return result


# 크롤링 함수
def crawling(game, use_redis=False):
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

                # redis 사용할때만 defense position 저장
                if use_redis:
                    defense_payload = build_defense_positions_payload(
                        game_id=game_id,
                        home_team=home,
                        away_team=away,
                        home_lineup=home_lineup,
                        away_lineup=away_lineup,
                    )
                    result["defense_positions"] = defense_payload

                merged_entries = create_merged_dict(entries, game_id)
        
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
                mark_game_status(game_id, 'done')
                return result, game_done

        except KeyError as e:
            print("경기 시작 전")
            break    

        except TypeError:
            mark_game_status(game_id, 'cancelled')
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
            result, game_done = crawling(game_id, True)

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
    today = datetime.datetime.today().date()  # 수정된 부분
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
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(crawl_game_loop, game_id, topic, producer) for game_id in new_game_id]

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

def get_game_datas(start_date, end_date):
    start = datetime.datetime.strptime(str(start_date), "%Y%m%d")
    end = datetime.datetime.strptime(str(end_date), "%Y%m%d")

    q = Q()
    current = start
    while current <= end:
        q |= Q(id__startswith=str(current.strftime("%Y%m%d")))
        current += datetime.timedelta(days=1)

    # 전체 날짜의 game_ids 한꺼번에 조회
    game_ids = models.Game.objects.filter(q).values_list('id', flat=True)
    print(game_ids)

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

def realtime_test():
    today = '20250810'
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
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(crawl_game_loop, game_id, topic, producer) for game_id in new_game_id]

        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"스레드 내부 에러: {e}")

def test():
    new_data, game_done = crawling('20250718HHKT02025')

    if new_data:
        for key in new_data.keys():
            if key == 'game_id' or key == 'game_over': continue
            else: print(new_data[key])
                
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
    # realtime_test()
    get_realtime_data()
    # get_all_game_datas(2021)
    # get_all_game_datas(2022)
    # get_all_game_datas(2023)
    # get_all_game_datas(2024)
    # get_all_game_datas(2025)
    # get_game_datas(20250711, 20250720)

if __name__ == "__main__":
    main()