# tasks.py
from rq import Queue
from redis import Redis
from helpers import process_raw_atbat_data, calculate_single_pli, AtBatData
from rq_queue import rq_redis

q = Queue(connection=rq_redis)

def calculate_pli_job(raw_data):
    processed = process_raw_atbat_data(raw_data)
    model = AtBatData(**processed)
    pli_val, li, base_we, w_total = calculate_single_pli(model)
    return {"pli": round(pli_val,4), "li": round(li,2), "base_we": round(base_we,4), "total_weight": round(w_total,4)}