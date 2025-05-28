import re
import requests

day_map = {
    0: "일요일",
    1: "월요일",
    2: "화요일",
    3: "수요일",
    4: "목요일",
    5: "금요일",
    6: "토요일"
}

team_map = {
    "KIA": "HT",
    "SSG": "SK",
    "LG": "LG",
    "NC": "NC",
    "KT": "KT",
    "롯데": "LT",
    "한화": "HH",
    "삼성": "SS",
    "키움": "WO",
    "두산": "OB"
}

field_map = {
    "잠실": "JS",
    "문학": "MH",
    "창원": "CW",
    "대전(신)": "DS",
    "대전": "DJ",
    "사직": "SJ",
    "수원": "SW",
    "울산": "WS",
    "포항": "PH",
    "고척": "GC",
    "청주": "CJ",
    "대구": "DG",
    "광주": "GJ"
}

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
            # 4: 주차, 6: 일자 (일요일부터 시작)
            temp = data['rows'][j]['row'][k]

            # 일자 출력 -> 월은 api에서 gamemonth
            text = temp['Text']
            day_match = re.search(r'<li class="dayNum">(\d+)</li>', text)
            day = day_match.group(1) if day_match else "?"
            print(f"\n{i}월 {day}일 {day_map[k]} 경기")

            # 종료된 경기일 경우
            if temp['Class']=='endGame':
                pattern = r"<li>(\S+)\s*<b>(\d+)\s*:\s*(\d+)</b>\s*(\S+)\s*<"

                # 1. 정규 경기 결과
                match_game = re.findall(r"<li>(\S+)\s*<b>(\d+)\s*:\s*(\d+)</b>\s*(\S+)", text)

                # 2. 취소 -> 우천 말고 폭염, 그라운드사정, 기타 취소 등등도 싹다 rainCancel로 뜸
                match_rain = re.findall(r"<li class='rainCancel'>(\S+)\s*:\s*(\S+)\s*\[(.*?)\]</li>", text)

                if match_game:
                    # print("진행된 경기:")
                    for t1, s1, s2, t2 in match_game:
                        t1 = team_map[t1]
                        t2 = team_map[t2]

                        print(f"{t1} {s1}:{s2} {t2}")

                if match_rain:
                    # print("\n취소된 경기:")
                    for t1, t2, stadium in match_rain:
                        t1 = team_map[t1]
                        t2 = team_map[t2]
                    
                        print(f"{t1} vs {t2} at {stadium} cancelled")

            # 종료되지 않은 경기일 경우  
            else:
                scheduled_games = re.findall(r"<li>(\S+)\s*:\s*(\S+)\s*\[(.*?)\]</li>", text)

                for t1, t2, stadium in scheduled_games:
                    t1 = team_map[t1]
                    t2 = team_map[t2]

                    print(f"{t1} vs {t2} at {stadium} scheduled")

                if not scheduled_games: print("경기 없음")