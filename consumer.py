from kafka import KafkaConsumer
import json
import psycopg2
import os
import django
import time

# os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ballrae_backend.settings")  # settings 모듈 경로 맞게 수정
# django.setup()

# from ballrae_backend.games.services import save_at_bat_transactionally

try:
    consumer = KafkaConsumer(
        '2025', 
        bootstrap_servers='kafka:9092',
        auto_offset_reset='latest',
        enable_auto_commit=True,
        group_id='db-save-group',
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        key_deserializer=lambda k: k.decode('utf-8') if k else None
    )

    while True:
        messages = consumer.poll(timeout_ms=10000)  # 20초 동안 메시지 기다림

        if messages:
            for tp, batch in messages.items():
                for message in batch:
                    print("* 받은 메시지:")
                    print(f"key: {message.key}")
                    print(f"value: {message.value}")

                    if message.key == "game_over" and message.value == True:
                        print("경기 종료, DB 저장 시작")
                        # DB 저장 시작

                        print("✅ DB NAME:", os.getenv("POSTGRES_DB"))

                        # conn = psycopg2.connect(
                        #     dbname=os.getenv("POSTGRES_DB"),
                        #     user=os.getenv("POSTGRES_USER"),
                        #     password=os.getenv("POSTGRES_PASSWORD"),
                        #     host=os.getenv("DB_HOST"),
                        #     port=os.getenv("DB_PORT") 
                        # )

                        # cur = conn.cursor()  # 커서 생성

                        # 직전 메시지 중 relay_data를 찾기
                        for m in batch:
                            if isinstance(m.value, dict):
                                relay_data = m.value
                                game_id = relay_data.get('game_id', 2025)  # 예시: 기본값 2025

                                game_id = "20250628SSWO02025"

                                for atbat in relay_data.get("at_bats", []):
                                    # pitch_sequence가 없거나 None이면 skip
                                    if not atbat.get("pitch_sequence"):
                                        continue

                                    game_dict = {
                                        "id": game_id,
                                        "home_team": relay_data.get("home_team", "HH"),
                                        "away_team": relay_data.get("away_team", "LG"),
                                        "date": game_id[:8],
                                        "score": "5:10"
                                    }

                                    inning_dict = {
                                        "inning_number": atbat["inning"],
                                        "half": atbat["half"],
                                    }

                                    player_dict = {
                                        "player_name": atbat["actual_batter"],
                                        "team_id": relay_data.get("team_id", "LG"),  # 예시
                                    }

                                    atbat_dict = {
                                        "bat_order": atbat["bat_order"],
                                        "result": atbat["result"],
                                        "appearance_num": atbat.get("appearance_number", 1),
                                    }

                                    pitch_list = []
                                    for pitch in atbat["pitch_sequence"]:
                                        pitch_list.append({
                                            "pitch_num": pitch.get("pitch_num"),
                                            "pitch_type": pitch.get("pitch_type"),
                                            "speed": float(pitch["speed"]) if pitch.get("speed") else None,
                                            "count": pitch.get("count"),
                                            "pitch_result": pitch.get("pitch_result"),
                                        })

                                    # save_at_bat_transactionally({
                                    #     "game": game_dict,
                                    #     "inning": inning_dict,
                                    #     "player": player_dict,
                                    #     "atbat": atbat_dict,
                                    #     "pitches": pitch_list,
                                    # })

                        break  # 저장 후 종료


        else:
            print("⏳ 새 메시지 없음")
            
except KeyboardInterrupt:
    print("🛑 컨슈머 종료 중...")
finally:
    consumer.close()