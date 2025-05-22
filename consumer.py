from kafka import KafkaConsumer
import json
import psycopg2
from dotenv import load_dotenv
import os

try:
    consumer = KafkaConsumer(
        '2025', 
        bootstrap_servers='kafka:9092',
        auto_offset_reset='earliest',
        enable_auto_commit=True,
        group_id='new-group',
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        key_deserializer=lambda k: k.decode('utf-8') if k else None
    )


    while True:
        # producer가 10초 간격이니까 10초랑 동일하게 하면 지연 문제가 있을 수 있어서, 5~7초 사이가 적절하다고 판단
        # 일단 7초로 진행하되 서비스 진행하다가 문제 있을 것 같으면 5초로 진행
        messages = consumer.poll(timeout_ms=7000)  # 7초 동안 메시지 기다림

        if messages:
            for tp, batch in messages.items():
                for message in batch:
                    print(f"\n* 받은 메시지:")
                    print(f"key: {message.key}")
                    print(f"value: {message.value}")

                    if message.key == "game_over" and message.value == True:
                        # 여기에 DB 저장 로직
                        ...

        else:
            print("⏳ 새 메시지 없음")

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

except KeyboardInterrupt:
    print("🛑 컨슈머 종료 중...")
finally:
    consumer.close()