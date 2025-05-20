from kafka import KafkaConsumer
import json
import psycopg2
from dotenv import load_dotenv
import os

consumer = KafkaConsumer(
    '2025', 
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

    if message.key == "game_over" and message.value == True:
        # DB 저장 시작

        # PostgreSQL 데이터베이스에 연결
        load_dotenv()

        conn = psycopg2.connect(
            dbname=os.getenv("POSTGRES_DB"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            host=os.getenv("POSTGRES_HOST"),  
            port=os.getenv("POSTGRES_PORT") 
        )
        
        cur = conn.cursor()  # 커서 생성

        print("연결이 완료되었습니다.")

        # # 테이블 생성
        # cur.execute("CREATE TABLE test (id serial PRIMARY KEY, num integer, data varchar);")

        # # 데이터 삽입
        # cur.execute("INSERT INTO test (num, data) VALUES (%s, %s)", (100, "abc'def"))

        # cur.execute("SELECT * FROM test;")  # 쿼리 실행
        # print(cur.fetchone())

        # # 커밋 및 연결 종료
        # conn.commit()
        # cur.close()

        conn.close()