from kafka import KafkaConsumer
import json
import os
import django
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ballrae_backend.settings")
django.setup()

from ballrae_backend.games.services import save_at_bat_transactionally

last_full_game_data = []

valid_keys = [f"{i}회초" for i in range(1, 12)] + [f"{i}회말" for i in range(1, 12)]

import json
# from .redis_client import redis_client

# def save_relay_to_redis(game_id: str, relay_data: dict):
#     """
#     전체 relay json을 Redis에 저장하는 함수
#     """
#     for half_key in ['top', 'bot']:
#         if half_key not in relay_data:
#             continue

#         half_inning = relay_data[half_key]
#         inning_number = half_inning["inning_number"]
#         inning_id = half_inning["id"]

#         # 이닝 전체 저장
#         inning_key = f"game:{game_id}:inning:{inning_number}:{half_key}"
#         redis_client.set(inning_key, json.dumps(half_inning))

#         atbat_ids = []

#         for atbat in half_inning["atbats"]:
#             atbat_id = atbat["id"]
#             atbat_key = f"game:{game_id}:atbat:{atbat_id}"
#             redis_client.set(atbat_key, json.dumps(atbat))
#             atbat_ids.append(atbat_id)

#             # pitch 저장
#             pitch_ids = []
#             for pitch in atbat["pitches"]:
#                 pitch_id = pitch["id"]
#                 pitch_key = f"game:{game_id}:pitch:{pitch_id}"
#                 redis_client.set(pitch_key, json.dumps(pitch))
#                 pitch_ids.append(pitch_id)

#             redis_client.rpush(f"game:{game_id}:atbat:{atbat_id}:pitches", *pitch_ids)

#         # atbat 리스트 저장
#         redis_client.rpush(f"game:{game_id}:inning:{inning_number}:{half_key}:atbats", *atbat_ids)

try:
    consumer = KafkaConsumer(
        '2025', 
        bootstrap_servers='kafka:9092',
        auto_offset_reset='earliest',
        enable_auto_commit=True,
        group_id='db-save-group',
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        key_deserializer=lambda k: k.decode('utf-8') if k else None
    )

    print("✅ Kafka Consumer 시작. 메시지를 기다립니다...")

    # consumer를 이터레이터로 사용하여 메시지를 하나씩 처리
    for message in consumer:
        print(f"* 받은 메시지: key='{message.key}'")

        if message.key in valid_keys:
            last_full_game_data.append(message.value)

        # # 'game_over' 키를 가진 메시지를 받으면 DB 저장 로직 실행
        # elif message.key == "game_over" and message.value is True:            
        #     if last_full_game_data:
            for data in last_full_game_data:
                    # 직전에 저장해둔 경기 데이터를 사용하여 DB에 저장
                save_at_bat_transactionally(data)
                # print("✅ DB 저장 성공!")
                # save_relay_to_redis(data)
        
        # if message.key == "game_over" and message.value is True: break

except KeyboardInterrupt:
    print("🛑 컨슈머 종료 중...")
finally:
    if 'consumer' in locals() and consumer:
        consumer.close()