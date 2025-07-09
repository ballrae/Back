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
                print("✅ DB 저장 성공!")

except KeyboardInterrupt:
    print("🛑 컨슈머 종료 중...")
finally:
    if 'consumer' in locals() and consumer:
        consumer.close()