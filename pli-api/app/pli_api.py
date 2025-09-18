import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import requests
import pytz
from datetime import datetime, timedelta
import ast
import requests
from rq.job import Job
from rq import Queue
from rq_queue import redis_client
from tasks import calculate_pli_job
from helpers import AtBatData, calculate_single_pli

q = Queue(connection=redis_client)

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
    return {"job_id": job.get_id()}

@app.get("/test")
async def test_endpoint():
    return {"message": "test endpoint works"}

@app.get("/job/{job_id}")
async def get_job_result(job_id: str):
    try:
        job = Job.fetch(job_id, connection=redis_client)
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
