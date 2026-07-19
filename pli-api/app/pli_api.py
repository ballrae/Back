import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import requests
import pytz
from datetime import datetime, timedelta
import ast
import requests
import json
import hashlib
from rq.job import Job
from rq import Queue
from rq_queue import redis_client, rq_redis
from tasks import calculate_pli_job
from helpers import (
    AtBatData, calculate_single_pli, process_raw_atbat_data,
    get_win_expectancy, batting_weather_weight, combine_weights,
    streak_weight, pinch_weight, ibb_focus_weight, error_momentum_weight,
)

q = Queue(connection=rq_redis)

# --- 5. API 인스턴스 생성 ---
app = FastAPI()

# --- 6. API 엔드포인트 정의 ---
@app.post("/calculate_pli")
async def calculate_pli_endpoint(data: AtBatData):
    pli_val, base_we, w_total = calculate_single_pli(data)
    return {"pli": pli_val, "base_we": base_we, "total_weight": w_total}

# --- 7. 원본 데이터를 처리하는 API 엔드포인트 ---
@app.post("/calculate_pli_raw")
async def calculate_pli_raw(raw_data: dict):
    job = q.enqueue(calculate_pli_job, raw_data)
    return {"job_id": job.id}  # RQ 2.x: get_id() 제거됨 → job.id

# --- 7-1. 원본 데이터를 동기적으로 즉시 계산하는 엔드포인트 ---
# /calculate_pli_raw 는 job_id 만 반환(비동기)하므로, 캐시/배치 경로처럼
# 결과를 바로 받아야 하는 호출자를 위한 동기 버전.
@app.post("/calculate_pli_raw_sync")
async def calculate_pli_raw_sync(raw_data: dict):
    # 특정 타석(필드 None/형식 불일치)에서 500이 나면 호출자가 재시도 폭주하므로,
    # 실패해도 200 + 마커로 응답해 재시도 스톰을 막는다(그 타석만 PLI 생략).
    try:
        processed = process_raw_atbat_data(raw_data)
        model = AtBatData(**processed)
        pli_val, base_we, w_total = calculate_single_pli(model)
        return {
            "pli": round(pli_val, 4),
            "base_we": round(base_we, 4),
            "total_weight": round(w_total, 4),
        }
    except Exception as e:
        print("calculate_pli_raw_sync error:", repr(e))
        return {"error": "pli_compute_failed", "detail": str(e)}

@app.get("/test")
async def test_endpoint():
    return {"message": "test endpoint works"}

# --- 벤치 A 전용: 외부 호출 없는 결정적 PLI 계산 ---
# 목적: Redis 캐시(히트) vs 재계산의 "서빙 지연"을 깨끗하게 비교하기 위함.
# 실제 calculate_single_pli 는 컨디션 API·기상청 API를 호출해 비결정적이고
# 고빈도/동시 부하 시 외부 서비스를 남용하게 되므로, 벤치에서는 그 두 외부
# 호출을 제외한(컨디션 가중치=1.0) 순수 가중치 계산만 재현한다.
# → 실제 라이브 재계산은 외부 API까지 포함해 더 비싸므로, 이 캐시 이득 수치는
#   보수적 하한(실제 이득은 더 큼)이다. 캐시 로직은 services._fetch_single_pli 와 동일 전략.
def _compute_pli_local(d: dict) -> dict:
    we_end = get_win_expectancy(
        d["inning"], d["half"], d["outs"], d["runners_code"], d["score_diff"]
    )
    base_we = we_end if we_end is not None else 0.5
    w_env = batting_weather_weight(d.get("temp_c"))
    w_situ = combine_weights(
        streak_weight(d.get("loss_streak")),
        pinch_weight(d.get("pinch_event", False)),
        ibb_focus_weight(d.get("intentional_walk", False)),
        error_momentum_weight(d.get("error_happened", False), d.get("next_batter_after_error", False)),
    )
    w_total = combine_weights(w_env, w_situ)  # personal(condition) 제외 = 외부호출 없음
    pli = round(float(base_we) * w_total, 4)
    if d["half"] == "top":
        return {"pli": round(1 - pli, 4), "base_we": round(1 - base_we, 4), "total_weight": round(w_total, 4)}
    return {"pli": pli, "base_we": round(base_we, 4), "total_weight": round(w_total, 4)}


@app.post("/bench/pli/nocache")
async def bench_pli_nocache(d: dict):
    """캐시 우회 — 매 요청 재계산."""
    return _compute_pli_local(d)


@app.post("/bench/pli/cached")
async def bench_pli_cached(d: dict):
    """Redis 캐시 적용 — 요청 해시로 캐시. services._fetch_single_pli 와 동일 전략."""
    key = "benchpli:" + hashlib.sha1(json.dumps(d, sort_keys=True).encode()).hexdigest()
    cached = redis_client.get(key)
    if cached:
        return json.loads(cached)
    res = _compute_pli_local(d)
    redis_client.setex(key, 3600, json.dumps(res))
    return res

@app.get("/job/{job_id}")
async def get_job_result(job_id: str):
    try:
        job = Job.fetch(job_id, connection=rq_redis)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Job fetch error: {e}")
    
    if job.is_finished:
        return {"status": "finished", "result": job.result}
    elif job.is_failed:
        return {"status": "failed", "error": str(job.exc_info)}
    else:
        return {"status": job.get_status()}
# async def calculate_pli_from_raw(raw_data: dict):
#     try:
#         # 원본 데이터를 가공하는 함수를 호출합니다.
#         # 이 함수가 모든 가중치 값을 실제 계산해서 반환할 것입니다.
#         processed_data = process_raw_atbat_data(raw_data)
#         print(processed_data)
        
#         # 가공된 데이터를 AtBatData 모델에 맞게 변환
#         atbat_data_model = AtBatData(**processed_data)
        
#         # 가공된 데이터를 PLI 계산 함수로 전달
#         pli_val, base_we, w_total = calculate_single_pli(atbat_data_model)
#         print(f"계산 결과 확인: pli={pli_val}, base_we={base_we}, w_total={w_total}")

#         return {
#             "pli": round(pli_val, 4),
#             "base_we": round(base_we, 4),
#             "total_weight": round(w_total, 4),
#         }

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
