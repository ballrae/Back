#!/usr/bin/env python3
"""
실시간 스트리밍 데이터 처리 성능 벤치마크 스크립트
PostgreSQL, Redis, Kafka의 처리 지연시간과 처리량을 측정합니다.

시뮬레이션:
- relay.json 파일이 15초 간격으로 계속 들어옴
- 최대 5개를 동시에 처리
- 60초 동안 스트리밍 진행
"""

import json
import time
import os
import sys
import django
import psycopg2
from kafka import KafkaProducer
from datetime import datetime, timedelta
import random
import threading
import queue
from concurrent.futures import ThreadPoolExecutor

# Django 설정
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ballrae_backend.settings")
django.setup()

from ballrae_backend.streaming.redis_client import redis_client


# ============================================================================
# 데이터베이스 연결 정보 (환경변수 또는 기본값 사용)
# ============================================================================
DB_HOST = os.getenv("DATABASE_HOST", "db")
DB_PORT = int(os.getenv("DATABASE_PORT", 5432))
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
DB_NAME = os.getenv("POSTGRES_DB", "postgres")

KAFKA_BROKERS = [os.getenv("KAFKA_BROKERS", "kafka:9092")]
KAFKA_TOPIC = "ballrae-streaming"
REDIS_TTL = 24 * 60 * 60  # 1하루 (consumer.py와 동일)

# 스트리밍 설정
STREAMING_DURATION = 60      # 60초 동안 스트리밍
STREAMING_INTERVAL = 15      # 15초 간격으로 파일 도착
MAX_CONCURRENT = 5          # 최대 5개 동시 처리


# ============================================================================
# 성능 통계 추적
# ============================================================================
class PerformanceStats:
    def __init__(self):
        self.lock = threading.Lock()
        self.processed_count = 0
        self.total_latency = 0
        self.min_latency = float('inf')
        self.max_latency = 0
        self.errors = 0
        self.start_time = None
        
    def add(self, latency: float, error: bool = False):
        with self.lock:
            self.processed_count += 1
            if not error:
                self.total_latency += latency
                self.min_latency = min(self.min_latency, latency)
                self.max_latency = max(self.max_latency, latency)
            else:
                self.errors += 1
    
    def get_stats(self):
        with self.lock:
            if self.processed_count == 0:
                return {
                    "count": 0,
                    "avg_latency": 0,
                    "min_latency": 0,
                    "max_latency": 0,
                    "throughput": 0,
                    "errors": 0,
                    "elapsed": 0
                }
            
            elapsed = time.time() - self.start_time
            success_count = self.processed_count - self.errors
            avg_latency = self.total_latency / success_count if success_count > 0 else 0
            throughput = self.processed_count / elapsed if elapsed > 0 else 0
            
            return {
                "count": self.processed_count,
                "avg_latency": avg_latency,
                "min_latency": self.min_latency if self.min_latency != float('inf') else 0,
                "max_latency": self.max_latency,
                "throughput": throughput,
                "errors": self.errors,
                "elapsed": elapsed
            }


# ============================================================================
# 1. Mock Relay Data Generation
# ============================================================================
def load_relay_json(file_path: str) -> dict:
    """relay.json 파일을 읽고 기본 구조를 반환합니다."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "gameId": "20250205_001",
            "homeTeam": "NC",
            "awayTeam": "KIA",
            "timestamp": datetime.now().isoformat()
        }


def generate_relay_data(batch_num: int, item_num: int) -> dict:
    """
    스트리밍 시뮬레이션용 단건 relay 데이터를 생성합니다.
    """
    return {
        "gameId": f"STREAMING_{batch_num}_{item_num}",
        "homeTeam": random.choice(["NC", "KIA", "SK", "HT", "OB", "KT", "LG", "SS"]),
        "awayTeam": random.choice(["NC", "KIA", "SK", "HT", "OB", "KT", "LG", "SS"]),
        "timestamp": datetime.now().isoformat(),
        "inning": random.randint(1, 9),
        "score_diff": random.randint(-5, 5),
        "home_score": random.randint(0, 15),
        "away_score": random.randint(0, 15),
        "outs": random.randint(0, 2),
        "data_index": f"{batch_num}_{item_num}"
    }


# ============================================================================
# 2. PostgreSQL Streaming Test
# ============================================================================
def test_postgresql_streaming() -> dict:
    """
    PostgreSQL 스트리밍 성능 테스트
    - Producer: 15초 간격으로 5개씩 큐에 넣음
    - Consumer: 즉시 처리 (도착부터 저장까지의 지연시간 측정)
    """
    print(f"\n[PostgreSQL Streaming Test]")
    print(f"  설정: {STREAMING_DURATION}초, {STREAMING_INTERVAL}초 간격, {MAX_CONCURRENT}개 동시")
    
    data_queue = queue.Queue()
    stats = PerformanceStats()
    stats.start_time = time.time()
    stop_event = threading.Event()
    
    # 테이블 초기화
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            connect_timeout=10
        )
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS streaming_benchmark CASCADE")
        cursor.execute("""
            CREATE TABLE streaming_benchmark (
                id TEXT PRIMARY KEY,
                data JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cursor.close()
        conn.close()
        print("  → 테스트 테이블 준비 완료")
    except Exception as e:
        print(f"✗ 테이블 초기화 실패: {e}")
        return {"count": 0, "avg_latency": 0, "min_latency": 0, "max_latency": 0, "throughput": 0, "errors": 0, "elapsed": 0}
    
    # Producer: 15초 간격으로 5개씩 생성
    def producer_thread():
        batch_num = 0
        start_time = time.time()
        while time.time() - start_time < STREAMING_DURATION:
            batch_num += 1
            for i in range(MAX_CONCURRENT):
                data = generate_relay_data(batch_num, i)
                arrival_time = time.time()  # 도착 시간 기록
                data_queue.put({"data": data, "arrival_time": arrival_time})
            
            print(f"  → [{int(time.time() - stats.start_time):2d}s] Batch #{batch_num} 도착 ({MAX_CONCURRENT}개)")
            
            # 15초 간격 유지
            elapsed = time.time() - start_time - (batch_num - 1) * STREAMING_INTERVAL
            if elapsed < STREAMING_INTERVAL:
                time.sleep(STREAMING_INTERVAL - elapsed)
        
        stop_event.set()
    
    # Consumer: 즉시 처리 (지연시간 측정)
    def consumer_thread():
        while not stop_event.is_set() or not data_queue.empty():
            try:
                item = data_queue.get(timeout=1)
                data = item["data"]
                arrival_time = item["arrival_time"]
                
                # PostgreSQL 저장
                try:
                    conn = psycopg2.connect(
                        host=DB_HOST,
                        port=DB_PORT,
                        user=DB_USER,
                        password=DB_PASSWORD,
                        database=DB_NAME,
                        connect_timeout=10
                    )
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO streaming_benchmark (id, data) VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET data = %s",
                        (data['gameId'], json.dumps(data), json.dumps(data))
                    )
                    conn.commit()
                    cursor.close()
                    conn.close()
                    
                    # 지연시간 = 저장 완료 시간 - 도착 시간
                    latency = time.time() - arrival_time
                    stats.add(latency, error=False)
                    
                except Exception as e:
                    print(f"    ✗ PostgreSQL 처리 오류: {str(e)[:50]}")
                    stats.add(-1, error=True)
                    
                data_queue.task_done()
            except queue.Empty:
                continue
    
    # Producer/Consumer 실행
    prod_thread = threading.Thread(target=producer_thread, daemon=True)
    consumer_threads = [threading.Thread(target=consumer_thread, daemon=True) for _ in range(MAX_CONCURRENT)]
    
    prod_thread.start()
    for t in consumer_threads:
        t.start()
    
    prod_thread.join()
    data_queue.join()
    
    # 테이블 정리
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            connect_timeout=10
        )
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS streaming_benchmark CASCADE")
        conn.commit()
        cursor.close()
        conn.close()
    except:
        pass
    
    return stats.get_stats()


# ============================================================================
# 3. Redis Streaming Test
# ============================================================================
def test_redis_streaming() -> dict:
    """
    Redis 스트리밍 성능 테스트
    - Producer: 15초 간격으로 5개씩 큐에 넣음
    - Consumer: 즉시 처리 (도착부터 저장까지의 지연시간 측정)
    """
    print(f"\n[Redis Streaming Test]")
    print(f"  설정: {STREAMING_DURATION}초, {STREAMING_INTERVAL}초 간격, {MAX_CONCURRENT}개 동시")
    
    data_queue = queue.Queue()
    stats = PerformanceStats()
    stats.start_time = time.time()
    stop_event = threading.Event()
    
    # Producer: 15초 간격으로 5개씩 생성
    def producer_thread():
        batch_num = 0
        start_time = time.time()
        while time.time() - start_time < STREAMING_DURATION:
            batch_num += 1
            for i in range(MAX_CONCURRENT):
                data = generate_relay_data(batch_num, i)
                arrival_time = time.time()  # 도착 시간 기록
                data_queue.put({"data": data, "arrival_time": arrival_time})
            
            print(f"  → [{int(time.time() - stats.start_time):2d}s] Batch #{batch_num} 도착 ({MAX_CONCURRENT}개)")
            
            # 15초 간격 유지
            elapsed = time.time() - start_time - (batch_num - 1) * STREAMING_INTERVAL
            if elapsed < STREAMING_INTERVAL:
                time.sleep(STREAMING_INTERVAL - elapsed)
        
        stop_event.set()
    
    # Consumer: 즉시 처리 (지연시간 측정)
    def consumer_thread():
        while not stop_event.is_set() or not data_queue.empty():
            try:
                item = data_queue.get(timeout=1)
                data = item["data"]
                arrival_time = item["arrival_time"]
                
                # Redis 저장
                try:
                    key = f"streaming:{data['gameId']}"
                    redis_client.set(key, json.dumps(data), ex=REDIS_TTL)
                    
                    # 지연시간 = 저장 완료 시간 - 도착 시간
                    latency = time.time() - arrival_time
                    stats.add(latency, error=False)
                    
                except Exception as e:
                    print(f"    ✗ Redis 처리 오류: {str(e)[:50]}")
                    stats.add(-1, error=True)
                    
                data_queue.task_done()
            except queue.Empty:
                continue
    
    # Producer/Consumer 실행
    prod_thread = threading.Thread(target=producer_thread, daemon=True)
    consumer_threads = [threading.Thread(target=consumer_thread, daemon=True) for _ in range(MAX_CONCURRENT)]
    
    prod_thread.start()
    for t in consumer_threads:
        t.start()
    
    prod_thread.join()
    data_queue.join()
    
    return stats.get_stats()


# ============================================================================
# 4. Kafka Streaming Test
# ============================================================================
def test_kafka_streaming() -> dict:
    """
    Kafka 스트리밍 성능 테스트
    - Producer: 15초 간격으로 5개씩 큐에 넣음
    - Consumer: 즉시 처리 (도착부터 전송까지의 지연시간 측정)
    """
    print(f"\n[Kafka Streaming Test]")
    print(f"  설정: {STREAMING_DURATION}초, {STREAMING_INTERVAL}초 간격, {MAX_CONCURRENT}개 동시")
    
    data_queue = queue.Queue()
    stats = PerformanceStats()
    stats.start_time = time.time()
    stop_event = threading.Event()
    
    # Kafka Producer 설정
    try:
        kafka_producer = KafkaProducer(
            bootstrap_servers=KAFKA_BROKERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        )
        print("  → Kafka 연결 성공")
    except Exception as e:
        print(f"✗ Kafka 연결 실패: {e}")
        return {"count": 0, "avg_latency": 0, "min_latency": 0, "max_latency": 0, "throughput": 0, "errors": 0, "elapsed": 0}
    
    # Producer: 15초 간격으로 5개씩 생성
    def producer_thread():
        batch_num = 0
        start_time = time.time()
        while time.time() - start_time < STREAMING_DURATION:
            batch_num += 1
            for i in range(MAX_CONCURRENT):
                data = generate_relay_data(batch_num, i)
                arrival_time = time.time()  # 도착 시간 기록
                data_queue.put({"data": data, "arrival_time": arrival_time})
            
            print(f"  → [{int(time.time() - stats.start_time):2d}s] Batch #{batch_num} 도착 ({MAX_CONCURRENT}개)")
            
            # 15초 간격 유지
            elapsed = time.time() - start_time - (batch_num - 1) * STREAMING_INTERVAL
            if elapsed < STREAMING_INTERVAL:
                time.sleep(STREAMING_INTERVAL - elapsed)
        
        stop_event.set()
    
    # Consumer: 즉시 처리 (지연시간 측정)
    def consumer_thread():
        while not stop_event.is_set() or not data_queue.empty():
            try:
                item = data_queue.get(timeout=1)
                data = item["data"]
                arrival_time = item["arrival_time"]
                
                # Kafka 전송
                try:
                    key = str(data['gameId']).encode('utf-8')
                    kafka_producer.send(KAFKA_TOPIC, key=key, value=data)
                    
                    # 지연시간 = 전송 완료 시간 - 도착 시간
                    latency = time.time() - arrival_time
                    stats.add(latency, error=False)
                    
                except Exception as e:
                    print(f"    ✗ Kafka 처리 오류: {str(e)[:50]}")
                    stats.add(-1, error=True)
                    
                data_queue.task_done()
            except queue.Empty:
                continue
    
    # Producer/Consumer 실행
    prod_thread = threading.Thread(target=producer_thread, daemon=True)
    consumer_threads = [threading.Thread(target=consumer_thread, daemon=True) for _ in range(MAX_CONCURRENT)]
    
    prod_thread.start()
    for t in consumer_threads:
        t.start()
    
    prod_thread.join()
    data_queue.join()
    
    kafka_producer.flush()
    kafka_producer.close()
    
    return stats.get_stats()


# ============================================================================
# 5. 결과 출력 및 비교
# ============================================================================
def print_results(pg_stats: dict, redis_stats: dict, kafka_stats: dict):
    """모든 성능 테스트 결과를 출력합니다."""
    print("\n" + "=" * 90)
    print("[ 실시간 스트리밍 데이터 처리 성능 벤치마크 결과 ]")
    print("=" * 90)
    
    print(f"\n테스트 설정:")
    print(f"  • 스트리밍 기간: {STREAMING_DURATION}초")
    print(f"  • 도착 간격: {STREAMING_INTERVAL}초")
    print(f"  • 동시 처리: {MAX_CONCURRENT}개")
    print(f"  • 총 배치: {STREAMING_DURATION // STREAMING_INTERVAL}개 (5개/배치 × {STREAMING_DURATION // STREAMING_INTERVAL}배치 = {(STREAMING_DURATION // STREAMING_INTERVAL) * MAX_CONCURRENT}건)")
    
    print(f"\n[1] PostgreSQL 성능")
    print(f"    총 처리: {pg_stats['count']:,}건")
    print(f"    성공률: {((pg_stats['count']-pg_stats['errors'])/pg_stats['count']*100):.1f}%" if pg_stats['count'] > 0 else "    성공률: 0%")
    print(f"    평균 지연: {pg_stats['avg_latency']*1000:.2f}ms")
    print(f"    최소/최대: {pg_stats['min_latency']*1000:.2f}ms / {pg_stats['max_latency']*1000:.2f}ms")
    print(f"    처리량: {pg_stats['throughput']:.2f} 건/초")
    
    print(f"\n[2] Redis 성능")
    print(f"    총 처리: {redis_stats['count']:,}건")
    print(f"    성공률: {((redis_stats['count']-redis_stats['errors'])/redis_stats['count']*100):.1f}%" if redis_stats['count'] > 0 else "    성공률: 0%")
    print(f"    평균 지연: {redis_stats['avg_latency']*1000:.2f}ms")
    print(f"    최소/최대: {redis_stats['min_latency']*1000:.2f}ms / {redis_stats['max_latency']*1000:.2f}ms")
    print(f"    처리량: {redis_stats['throughput']:.2f} 건/초")
    
    print(f"\n[3] Kafka 성능")
    print(f"    총 처리: {kafka_stats['count']:,}건")
    print(f"    성공률: {((kafka_stats['count']-kafka_stats['errors'])/kafka_stats['count']*100):.1f}%" if kafka_stats['count'] > 0 else "    성공률: 0%")
    print(f"    평균 지연: {kafka_stats['avg_latency']*1000:.2f}ms")
    print(f"    최소/최대: {kafka_stats['min_latency']*1000:.2f}ms / {kafka_stats['max_latency']*1000:.2f}ms")
    print(f"    처리량: {kafka_stats['throughput']:.2f} 건/초")
    
    print(f"\n[성능 비교 분석]")
    print("-" * 90)
    
    # 지연시간 비교
    if pg_stats['avg_latency'] > 0 and redis_stats['avg_latency'] > 0:
        ratio = pg_stats['avg_latency'] / redis_stats['avg_latency']
        print(f"• 지연시간: Redis는 PostgreSQL 대비 약 {ratio:.2f}배 빠릅니다.")
    
    if redis_stats['avg_latency'] > 0 and kafka_stats['avg_latency'] > 0:
        ratio = kafka_stats['avg_latency'] / redis_stats['avg_latency']
        print(f"           Kafka는 Redis 대비 약 {ratio:.2f}배 {'느립니다' if ratio > 1 else '빠릅니다'}.")
    
    # 처리량 비교
    if pg_stats['throughput'] > 0 and redis_stats['throughput'] > 0:
        ratio = redis_stats['throughput'] / pg_stats['throughput']
        print(f"• 처리량: Redis는 PostgreSQL 대비 약 {ratio:.2f}배 빠릅니다.")
    
    if redis_stats['throughput'] > 0 and kafka_stats['throughput'] > 0:
        ratio = redis_stats['throughput'] / kafka_stats['throughput']
        print(f"          Redis는 Kafka 대비 약 {ratio:.2f}배 빠릅니다.")
    
    print("\n" + "=" * 90)
    print(f"테스트 완료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 90)


# ============================================================================
# Main 실행
# ============================================================================
def main():
    print("=" * 90)
    print("실시간 스트리밍 데이터 처리 성능 벤치마크 시작")
    print("=" * 90)
    
    # 1. PostgreSQL Streaming 테스트
    pg_stats = test_postgresql_streaming()
    time.sleep(2)
    
    # 2. Redis Streaming 테스트
    redis_stats = test_redis_streaming()
    time.sleep(2)
    
    # 3. Kafka Streaming 테스트
    kafka_stats = test_kafka_streaming()
    time.sleep(2)
    
    # 4. 결과 출력
    print_results(pg_stats, redis_stats, kafka_stats)


if __name__ == "__main__":
    main()
