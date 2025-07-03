import requests
import time

def filter_text(text: str) -> str:
    try:
        start = time.time()  # ⏱ 시작 시간 기록

        response = requests.post(
            "http://hate-filter-api:8001/filter",  # 도커 서비스 이름으로 요청
            json={"text": text},
            timeout=2
        )

        end = time.time()  # ⏱ 종료 시간 기록
        print(f"[필터 응답 시간] {end - start:.3f}초 | 원문: {text}")

        if response.status_code == 200:
            return response.json().get("masked_text", text)
        return text
    except Exception as e:
        print("욕설 필터링 실패:", e)
        return text