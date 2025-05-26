import re
import requests

url = "https://www.koreabaseball.com/ws/Schedule.asmx/GetMonthSchedule?leId=1&srIdList=0,1,3,4,5,7,9,6&seasonId=2025&gameMonth=05"
headers = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.koreabaseball.com/ws/Schedule.asmx/"
}

response = requests.get(url, headers=headers)
data = response.json()

# 4: 주차, 6: 일자 (일요일부터 시작)
temp = data['rows'][4]['row'][6]

# 일자 출력 -> 월은 api에서 gamemonth
text = temp['Text']
day_match = re.search(r'<li class="dayNum">(\d+)</li>', text)
day = day_match.group(1) if day_match else "?"
print(f"{day}일 경기")

# 종료된 경기일 경우
if temp['Class']=='endGame':
    pattern = r"<li>(\S+)\s*<b>(\d+)\s*:\s*(\d+)</b>\s*(\S+)\s*<"

    # 1. 정규 경기 결과
    match_game = re.findall(r"<li>(\S+)\s*<b>(\d+)\s*:\s*(\d+)</b>\s*(\S+)", text)

    # 2. 취소 -> 우천 말고 폭염, 그라운드사정, 기타 취소 등등도 싹다 rainCancel로 뜸
    match_rain = re.findall(r"<li class='rainCancel'>(\S+)\s*:\s*(\S+)\s*\[(.*?)\]</li>", text)

    print("진행된 경기:")
    for t1, s1, s2, t2 in match_game:
        print(f"{t1} {s1}:{s2} {t2}")

    print("\n취소된 경기:")
    for t1, t2, stadium in match_rain:
        print(f"{t1} vs {t2} at {stadium} cancelled")

# 종료되지 않은 경기일 경우  
else:
    scheduled_games = re.findall(r"<li>(\S+)\s*:\s*(\S+)\s*\[(.*?)\]</li>", text)

    for t1, t2, stadium in scheduled_games:
        print(f"{t1} vs {t2} at {stadium} scheduled")