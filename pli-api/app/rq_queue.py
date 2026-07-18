import redis
import os

_HOST = os.getenv("REDIS_HOST", "ballrae-redis")
_PORT = int(os.getenv("REDIS_PORT", 6379))

# 앱 캐시용(문자열 편의). 기상청 캐시 등 일반 GET/SET 에 사용.
redis_client = redis.Redis(host=_HOST, port=_PORT, db=0, decode_responses=True)

# RQ 전용 연결: RQ 는 pickle 바이너리를 다루므로 decode_responses 를 켜면
# Job.fetch 가 깨져 404 가 난다. 반드시 decode_responses 없이(bytes) 사용.
rq_redis = redis.Redis(host=_HOST, port=_PORT, db=0)