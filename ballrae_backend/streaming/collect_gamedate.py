import re
import requests
import psycopg2
import os
from dotenv import load_dotenv
from collections import defaultdict
from psycopg2.errors import UniqueViolation
import datetime
from datetime import datetime
from holidayskr import is_holiday

def set_game_time(date):
    # time 객체에 날짜 설정
    time = date

    # 월, 요일, 시간 추출
    month = time.month
    weekday = time.weekday()  # 0: 월요일, 1: 화요일, ..., 6: 일요일

    # 날짜를 문자열 형식으로 변환 (YYYY-MM-DD)
    holiday_str = time.strftime("%Y-%m-%d")

    # 공휴일 여부 확인 (is_holiday 함수 사용)
    holiday = is_holiday(holiday_str)

    # 기본 시간 설정 (기본적으로 18:30)
    time = time.replace(hour=18, minute=30)

    # 조건에 맞는 시간 설정
    if weekday == 5:  # 토요일
        if month == 7 or month == 8:
            time = time.replace(hour=18, minute=0)  # 17:00
        else: time = time.replace(hour=17, minute=0)

    elif weekday == 6 or holiday:  # 일요일
        if month == 6:  # 6월
            time = time.replace(hour=17, minute=0)  # 17:00
        elif month == 7 or month == 8:
            time = time.replace(hour=18, minute=0)
        else: time = time.replace(hour=14, minute=0)  # 14:00 (일요일)

    else:
        time = time.replace(hour=18, minute=30)  # 기본 18:30
    
    return time

# 설정
load_dotenv()
conn = psycopg2.connect(
    dbname=os.getenv("POSTGRES_DB"),
    user=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT") 
)
cur = conn.cursor()
print("DB 연결이 완료되었습니다.")

# 매핑
team_map = {
    "KIA": "KA", "SSG": "SL", "LG": "LG", "NC": "NC", "KT": "KT",
    "롯데": "LT", "한화": "HH", "삼성": "SS", "키움": "HE", "두산": "DS",
    
}

field_map = {
    "잠실": "JS", "문학": "MH", "창원": "CW", "대전(신)": "DS", "대전": "DJ", 
    "사직": "SJ", "수원": "SW", "울산": "WS", "포항": "PH", "고척": "GC", "청주": "CJ", 
    "대구": "DG", "광주": "GJ"
    }

# for year in [2023, 2024, 2025]:
for year in [2021, 2022]:
    # 월 단위 크롤링
    for i in range(3, 11):
        print(i, "월")
        try:
            url = f"https://www.koreabaseball.com/ws/Schedule.asmx/GetMonthSchedule?leId=1&srIdList=0,1,3,4,5,7,9,6&seasonId={year}&gameMonth={str(i).zfill(2)}"
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.koreabaseball.com/ws/Schedule.asmx/"
            }

            response = requests.get(url, headers=headers)
            data = response.json()

            for j in range(6):
                for k in range(7):
                    temp = data['rows'][j]['row'][k]
                    text = temp['Text']
                    day_match = re.search(r'<li class="dayNum">(\d+)</li>', text)
                    if not day_match:
                        continue

                    day = int(day_match.group(1))
                    date = f"{year}{i:02d}{day:02d}"

                    time = datetime.strptime(date, "%Y%m%d")
                    
                    time = set_game_time(time)

                    # 경기 그룹 저장 (key: (home, away))
                    game_entries = defaultdict(list)

                    # 종료된 경기
                    if temp['Class'] == 'endGame':
                        matches = re.findall(r"<li>(\S+)\s*<b>(\d+)\s*:\s*(\d+)</b>\s*(\S+)", text)
                        for away, s1, s2, home in matches:
                            if away in ['드림', '나눔'] or home in ['드림', '나눔']:
                                print(f"올스타전 또는 특수경기 스킵됨: {away} vs {home}")
                                continue
                            away, home = team_map[away], team_map[home]
                            game_entries[(home, away)].append({
                                "status": "done",
                                "score": f"{s1}:{s2}"
                            })

                        cancels = re.findall(r"<li class='rainCancel'>(\S+)\s*:\s*(\S+)\s*\[(.*?)\]</li>", text)
                        for away, home, _ in cancels:
                            if away in ['드림', '나눔'] or home in ['드림', '나눔']:
                                print(f"올스타전 또는 특수경기 스킵됨: {away} vs {home}")
                                continue
                            away, home = team_map[away], team_map[home]
                            game_entries[(home, away)].append({
                                "status": "cancelled"
                            })

                    # 예정된 경기
                    else:
                        matches = re.findall(r"<li>(\S+)\s*:\s*(\S+)\s*\[(.*?)\]</li>", text)
                        for away, home, _ in matches:
                            if away in ['드림', '나눔'] or home in ['드림', '나눔']:
                                print(f"올스타전 또는 특수경기 스킵됨: {away} vs {home}")
                                continue
                            away, home = team_map[away], team_map[home]
                            game_entries[(home, away)].append({
                                "status": "scheduled"
                            })

                    # DB 저장
                    for (home, away), entries in game_entries.items():
                        for idx, entry in enumerate(entries):
                            dh = idx + 1 if len(entries) > 1 else 0
                            game_id = f"{date}{away}{home}{dh}2025"

                            try:
                                cur.execute("SELECT status FROM games_game WHERE id = %s", (game_id,))
                                existing = cur.fetchone()

                                if existing is None:
                                    # 존재하지 않는 경우 insert
                                    if entry["status"] == "done":
                                        cur.execute("""
                                            INSERT INTO games_game (id, status, dh, score, date, home_team, away_team)
                                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                                        """, (game_id, "done", dh, entry["score"], time, home, away))
                                    elif entry["status"] == "cancelled":
                                        cur.execute("""
                                            INSERT INTO games_game (id, status, dh, date, home_team, away_team)
                                            VALUES (%s, %s, %s, %s, %s, %s)
                                        """, (game_id, "cancelled", dh, time, home, away))
                                    elif entry["status"] == "scheduled":
                                        cur.execute("""
                                            INSERT INTO games_game (id, status, dh, date, home_team, away_team)
                                            VALUES (%s, %s, %s, %s, %s, %s)
                                        """, (game_id, "scheduled", dh, time, home, away))

                                elif existing[0] == "scheduled":
                                    # 존재하고 status가 scheduled면 update
                                    if entry["status"] == "done":
                                        cur.execute("""
                                            UPDATE games_game
                                            SET status = %s, score = %s
                                            WHERE id = %s
                                        """, ("done", entry["score"], game_id))
                                    elif entry["status"] == "cancelled":
                                        cur.execute("""
                                            UPDATE games_game
                                            SET status = %s
                                            WHERE id = %s
                                        """, ("cancelled", game_id))

                            except Exception as e:
                                conn.rollback()
                                print(f"오류 발생: {game_id} -> {e}")
                            else:
                                conn.commit()
                        
        except Exception as e:
            print(e)
            continue

cur.close()
conn.close()
