from kafka import KafkaConsumer
import json

consumer = KafkaConsumer(
    '2025',  # ✅ 너가 producer에서 사용한 topic 이름과 같아야 함
    bootstrap_servers='localhost:9092',
    auto_offset_reset='earliest',
    enable_auto_commit=True,
    group_id='new-group',
    value_deserializer=lambda x: json.loads(x.decode('utf-8')),
    key_deserializer=lambda k: k.decode('utf-8') if k else None
)

print("✅ Kafka consumer 시작됨. 메시지 기다리는 중...")

for message in consumer:
    print(f"\n🟡 받은 메시지:")
    print(f"🔑 key: {message.key}")
    print(f"📦 value: {message.value}")