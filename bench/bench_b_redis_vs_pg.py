#!/usr/bin/env python3
"""
Bench B — 조회 속도: Redis GET vs PostgreSQL 직접 SELECT.

주장 ②("RDBMS 직접 조회 대비 10배 이상 빠름") 검증.

같은 데이터(실제 한 이닝의 atbats + pitches)를
  - PostgreSQL: psycopg2 로 직접 SELECT 해서 이닝 payload 구성
  - Redis: 동일 payload 를 GET + json 파싱
각각 워밍업 100회 후 1,000회 조회해 latency 비교, 배율(pg_mean / redis_mean).

측정은 in-process(순수 psycopg2 + redis)로 수행 — Django ORM/DEBUG 오버헤드를
배제해 "저장소 조회 자체"를 공정하게 비교. 커넥션은 1회 열어 재사용(현실적 풀링).
"""
import os
import sys
import time
import json
import argparse

sys.path.insert(0, os.path.dirname(__file__))
import common  # noqa: E402
import psycopg2  # noqa: E402
import redis  # noqa: E402

DB = dict(
    host=os.getenv("DB_HOST", "db"),
    port=int(os.getenv("DB_PORT", 5432)),
    user=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
    dbname=os.getenv("POSTGRES_DB"),
)
REDIS = dict(
    host=os.getenv("REDIS_HOST", "ballrae-redis"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
)


def pick_inning(cur):
    cur.execute(
        "SELECT inning_id, count(*) c FROM games_atbat "
        "GROUP BY inning_id HAVING count(*) >= 5 ORDER BY inning_id LIMIT 1"
    )
    row = cur.fetchone()
    if not row:
        raise SystemExit("atbat 이 5개 이상인 이닝이 없습니다. 먼저 경기 기록을 적재하세요.")
    return row[0], row[1]


def pg_fetch(cur, inning_id) -> dict:
    """PostgreSQL 직접 SELECT 로 이닝 payload 구성 (atbats + pitches)."""
    cur.execute(
        'SELECT id, bat_order, pitcher, "out", score, on_base, main_result, '
        'full_result, strike_zone FROM games_atbat WHERE inning_id = %s ORDER BY id',
        (inning_id,),
    )
    atbat_rows = cur.fetchall()
    cur.execute(
        "SELECT at_bats_id, pitch_num, pitch_type, speed, count, pitch_result "
        "FROM games_pitch WHERE at_bats_id IN "
        "(SELECT id FROM games_atbat WHERE inning_id = %s) ORDER BY at_bats_id, pitch_num",
        (inning_id,),
    )
    pitch_rows = cur.fetchall()

    pitches_by_ab: dict = {}
    for pr in pitch_rows:
        pitches_by_ab.setdefault(pr[0], []).append({
            "pitch_num": pr[1], "pitch_type": pr[2], "speed": pr[3],
            "count": pr[4], "pitch_result": pr[5],
        })

    atbats = []
    for a in atbat_rows:
        atbats.append({
            "id": a[0], "bat_order": a[1], "pitcher": a[2], "out": a[3], "score": a[4],
            "on_base": a[5], "main_result": a[6], "full_result": a[7], "strike_zone": a[8],
            "pitches": pitches_by_ab.get(a[0], []),
        })
    return {"inning_id": inning_id, "atbats": atbats}


def bench_loop(fn, warmup, iters) -> list[float]:
    for _ in range(warmup):
        fn()
    lats = []
    for _ in range(iters):
        t0 = time.perf_counter()
        fn()
        lats.append((time.perf_counter() - t0) * 1000.0)
    return lats


def measure_once(cur, r, inning_id, rkey, warmup, iters) -> list[dict]:
    pg_lats = bench_loop(lambda: pg_fetch(cur, inning_id), warmup, iters)
    redis_lats = bench_loop(lambda: json.loads(r.get(rkey)), warmup, iters)
    pg = common.summarize(pg_lats)
    rd = common.summarize(redis_lats)
    ratio = round(pg["mean"] / rd["mean"], 2) if rd["mean"] > 0 else None
    return [
        {"path": "postgresql_select", "latency_ms": pg},
        {"path": "redis_get", "latency_ms": rd, "speedup_over_pg": ratio},
    ]


def main():
    ap = argparse.ArgumentParser(description="Bench B — Redis GET vs PostgreSQL SELECT")
    ap.add_argument("--warmup", type=int, default=100)
    ap.add_argument("--iters", type=int, default=1000)
    ap.add_argument("--runs", type=int, default=5, help="전체 측정 반복 횟수(런 간 편차용)")
    args = ap.parse_args()

    conn = psycopg2.connect(**DB)
    conn.autocommit = True
    cur = conn.cursor()
    r = redis.Redis(**REDIS, decode_responses=True)

    inning_id, ab_count = pick_inning(cur)
    payload = pg_fetch(cur, inning_id)
    pitch_count = sum(len(a["pitches"]) for a in payload["atbats"])
    rkey = f"benchb:inning:{inning_id}"
    r.set(rkey, json.dumps(payload, ensure_ascii=False))

    cur.execute("SELECT (SELECT count(*) FROM games_atbat), (SELECT count(*) FROM games_pitch)")
    tot_ab, tot_pitch = cur.fetchone()
    cur.execute("SELECT version()")
    pg_version = cur.fetchone()[0].split(",")[0]

    env = common.capture_env({
        "redis_version": r.info().get("redis_version"), "postgres_version": pg_version,
        "sample_inning_id": inning_id, "sample_inning_atbats": ab_count,
        "sample_inning_pitches": pitch_count, "total_atbats": tot_ab, "total_pitches": tot_pitch,
        "warmup": args.warmup, "iters": args.iters, "concurrency": 1, "n_runs": args.runs,
    })
    print("측정 환경:", json.dumps(env, ensure_ascii=False))

    runs = []
    ratios = []
    for i in range(args.runs):
        print(f"--- run {i+1}/{args.runs} ---")
        sc = measure_once(cur, r, inning_id, rkey, args.warmup, args.iters)
        runs.append(sc)
        ratios.append(sc[1]["speedup_over_pg"])

    run_agg = common.aggregate_runs(runs, ["path"], "latency_ms.mean")
    import statistics
    payload_out = {
        "bench": "B_redis_vs_postgresql", "env": env,
        "n_runs": args.runs, "runs": runs, "run_aggregation": run_agg,
        "speedup_redis_over_pg_median": round(statistics.median(ratios), 2) if ratios else None,
        "speedup_run_spread": [min(ratios), max(ratios)] if ratios else None,
        "scenarios": run_agg,
    }
    json_path, csv_path = common.write_results("bench_b", payload_out)

    last = runs[-1]
    pg, rd = last[0]["latency_ms"], last[1]["latency_ms"]
    common.print_table(
        ["path", "mean", "p50", "p95", "p99", "min", "max"],
        [["postgresql_select", pg["mean"], pg["p50"], pg["p95"], pg["p99"], pg["min"], pg["max"]],
         ["redis_get", rd["mean"], rd["p50"], rd["p95"], rd["p99"], rd["min"], rd["max"]]],
        title="=== Bench B 마지막 런 (지연 ms) ===",
    )
    rows2 = [[a["path"], a["n_runs"], a["median_of_means"], f'{a["run_spread"][0]}~{a["run_spread"][1]}']
             for a in run_agg]
    common.print_table(["path", "n_runs", "median_of_means", "run_spread(min~max)"],
                       rows2, title="=== Bench B 런 간 편차 (mean 지연 ms) ===")
    print(f"\nRedis vs PostgreSQL 배율: median {payload_out['speedup_redis_over_pg_median']}x, "
          f"스프레드 {payload_out['speedup_run_spread']}")
    print(f"\n결과 저장:\n  {json_path}\n  {csv_path}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
