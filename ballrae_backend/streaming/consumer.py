from kafka import KafkaConsumer
import json
import os
import django
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ballrae_backend.settings")
django.setup()

from ballrae_backend.games.services import save_at_bat_transactionally
from streaming.redis_client import redis_client

DEFAULT_TTL = 24 * 60 * 60  # 하루

# ---- 추가: 메시지 -> Redis 저장 스키마로 정규화 ----
def normalize_for_redis(msg: dict) -> dict:
    game_id = msg.get("game_id")
    inning = msg.get("inning")
    half = msg.get("half")  # "top" or "bot"
    atbats = msg.get("at_bats", [])

    payload = {"game_id": game_id}
    half_block = {
        "game": game_id,
        "inning_number": inning,
        # "id": f"{game_id}:{inning}:{half}",  # 필요하면 사용
        "atbats": atbats,
    }
    # half에 맞는 키로 넣기
    if half == "top":
        payload["top"] = half_block
    elif half == "bot":
        payload["bot"] = half_block
    return payload

def _save_half_inning(half_inning, half_key):
    inning_number = half_inning["inning_number"]
    game_id = half_inning["game"]

    print(f"🔎 Redis 저장: {game_id} {inning_number}회 {half_key} / atbats {len(half_inning.get('atbats', []))}")

    inning_key = f"game:{game_id}:inning:{inning_number}:{half_key}"
    redis_client.set(inning_key, json.dumps(half_inning), ex=DEFAULT_TTL)
    print(f"✅ 저장 완료: {inning_key}")
    
def save_relay_to_redis(relay_data: dict):
    print(f"Redis 저장 시도: {relay_data.get('game_id')}")
    try:
        for half_key in ['top', 'bot']:
            if half_key not in relay_data:
                # print(f"⚠️ half_key '{half_key}' 없음 → 다음으로 넘어감.")
                continue

            half_inning = relay_data[half_key]
            inning_number = half_inning["inning_number"]
            game_id = half_inning['game']

            print(f"🔎 Redis 저장: {game_id} {inning_number}회 {half_key} / atbats {len(half_inning.get('atbats', []))}")

            inning_key = f"game:{game_id}:inning:{inning_number}:{half_key}"
            redis_client.set(inning_key, json.dumps(half_inning), ex=DEFAULT_TTL)
            print(f"✅ 저장 완료: {inning_key}")

    except Exception as e:
        print(f"❌ Redis 저장 실패: {e}")

def save_defense_positions_to_redis(payload, ttl=DEFAULT_TTL):
    game_id   = payload.get("game_id")
    home_team = payload.get("home_team")
    away_team = payload.get("away_team")
    if not game_id or not home_team or not away_team:
        return

    def write_team_hash(team_code: str, side_list):
        # 원하는 키 이름 그대로 사용
        key = f"defense_position:{game_id}:{team_code}"

        # pcode -> pos 매핑으로 통으로 덮어쓰기(이전 잔여 데이터 방지)
        mapping = {str(it["pcode"]): str(it["pos"])
                   for it in (side_list or [])
                   if it.get("pcode") and it.get("pos")}
        
        print(f"[DEBUG] {team_code} mapping: {mapping}")
        
        pipe = redis_client.pipeline()
        pipe.delete(key)                         # 기존 값 제거(원자적 교체)
        if mapping:
            pipe.hset(key, mapping=mapping)      # 해시에 한 번에 입력
        pipe.expire(key, ttl)                    # TTL 설정
        pipe.execute()

    write_team_hash(home_team, payload.get("home"))
    write_team_hash(away_team, payload.get("away"))
    print(f"✅ 수비 포지션 저장 완료: {game_id} (해시 2개)")

valid_keys = [f"{i}회초" for i in range(1, 12)] + [f"{i}회말" for i in range(1, 12)]

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

    for message in consumer:
        print(f"* 받은 메시지: key='{message.key}'")

        if message.key in valid_keys:
            payload = normalize_for_redis(message.value)
            save_relay_to_redis(relay_data=payload)

        elif message.key == "defense_positions":
            save_defense_positions_to_redis(message.value)

except KeyboardInterrupt:
    print("🛑 컨슈머 종료 중...")
finally:
    if 'consumer' in locals() and consumer:
        consumer.close()