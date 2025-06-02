import re
import requests
import psycopg2
import os
from dotenv import load_dotenv
from collections import defaultdict
from psycopg2.errors import UniqueViolation

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
    "KIA": "HT", "SSG": "SK", "LG": "LG", "NC": "NC", "KT": "KT",
    "롯데": "LT", "한화": "HH", "삼성": "SS", "키움": "WO", "두산": "OB"
}

field_map = {
    "잠실": "JS", "문학": "MH", "창원": "CW", "대전(신)": "DS", "대전": "DJ", 
    "사직": "SJ", "수원": "SW", "울산": "WS", "포항": "PH", "고척": "GC", "청주": "CJ", 
    "대구": "DG", "광주": "GJ"
    }

# 월 단위 크롤링
for i in range(3, 11):
    url = f"https://www.koreabaseball.com/ws/Schedule.asmx/GetMonthSchedule?leId=1&srIdList=0,1,3,4,5,7,9,6&seasonId=2025&gameMonth={str(i).zfill(2)}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.koreabaseball.com/ws/Schedule.asmx/"
    }

    response = requests.get(url, headers=headers)
    data = response.json()

    for j in range(5):
        for k in range(7):
            temp = data['rows'][j]['row'][k]
            text = temp['Text']
            day_match = re.search(r'<li class="dayNum">(\d+)</li>', text)
            if not day_match:
                continue

            day = int(day_match.group(1))
            date = f"2025{i:02d}{day:02d}"

            # 경기 그룹 저장 (key: (home, away))
            game_entries = defaultdict(list)

            # 종료된 경기
            if temp['Class'] == 'endGame':
                matches = re.findall(r"<li>(\S+)\s*<b>(\d+)\s*:\s*(\d+)</b>\s*(\S+)", text)
                for away, s1, s2, home in matches:
                    away, home = team_map[away], team_map[home]
                    game_entries[(home, away)].append({
                        "status": "done",
                        "score": f"{s1}:{s2}"
                    })

                cancels = re.findall(r"<li class='rainCancel'>(\S+)\s*:\s*(\S+)\s*\[(.*?)\]</li>", text)
                for away, home, _ in cancels:
                    away, home = team_map[away], team_map[home]
                    game_entries[(home, away)].append({
                        "status": "cancelled"
                    })

            # 예정된 경기
            else:
                matches = re.findall(r"<li>(\S+)\s*:\s*(\S+)\s*\[(.*?)\]</li>", text)
                for away, home, _ in matches:
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
                        if entry["status"] == "done":
                            cur.execute("""
                                INSERT INTO relay_game (id, status, dh, score, date, home_team, away_team)
                                VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """, (game_id, "done", dh, entry["score"], date, home, away))

                        elif entry["status"] == "cancelled":
                            cur.execute("""
                                INSERT INTO relay_game (id, status, dh, date, home_team, away_team)
                                VALUES (%s, %s, %s, %s, %s, %s)
                            """, (game_id, "cancelled", dh, date, home, away))

                        elif entry["status"] == "scheduled":
                            cur.execute("""
                                INSERT INTO relay_game (id, status, dh, date, home_team, away_team)
                                VALUES (%s, %s, %s, %s, %s, %s)
                            """, (game_id, "scheduled", dh, date, home, away))

                    except UniqueViolation:
                        conn.rollback()
                        print(f"중복으로 무시됨: {game_id}")

    conn.commit()

cur.close()
conn.close()