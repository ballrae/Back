#!/usr/bin/env python3
"""
Bench A — PLI 서빙 지연: Redis 캐시 효과 측정 (외부 API 포함 완전판).

주장 ①("Redis 캐싱으로 서빙 지연 51% 단축, 평균 21.36ms") 검증.

경로:
  nocache      POST /bench/pli/nocache      — 재계산(외부호출 제외, 결정적)
  cached       POST /bench/pli/cached       — Redis 캐시 히트
  nocache_real POST /calculate_pli_raw_sync — 실제 프로덕션 재계산(기상청+컨디션 외부호출 포함)

- nocache/cached: 동일 입력, 워밍업 100 + 1,000회, 순차(1)+동시(10,50). 외부호출 없음(결정적).
  → 계산 자체가 빨라 캐시 이득이 작게 나옴(정직한 하한). p50/95/99 포함.
- nocache_real: **완전판**. 실제 재계산 경로를 워밍업+반복+동시성으로 측정, 퍼센타일 산출.
  캐시 히트(cached) 대비 감소율 = reduction_pct_cached_vs_real. 이게 "캐시의 진짜 가치".
  ⚠️ 매 호출이 기상청(정부) API를 때리므로 rate-limit 방지 위해 반복/동시성 기본값은 보수적.
  재계산 경로가 외부 API 때문에 고동시성 확장이 불가한 것 자체가 "캐시가 필수인 이유".
  실호출이 전부 실패하면 관측 로그 기반 상수로 대체(임의 mock 아님).

--runs N: 전체 측정을 N회 반복하고 런 간 median/스프레드를 함께 출력·저장.

httpx+asyncio: 저장소 기존 의존성, 동시성 정밀 제어, 별도 설치 불필요.
"""
import os
import sys
import time
import json
import asyncio
import argparse

sys.path.insert(0, os.path.dirname(__file__))
import common  # noqa: E402
import httpx  # noqa: E402

PAYLOAD = {
    "inning": 9, "half": "bot", "outs": 1, "runners_code": "100", "score_diff": 0,
    "temp_c": 25.0, "loss_streak": 0, "pinch_event": False,
    "intentional_walk": False, "error_happened": False, "next_batter_after_error": False,
}

REAL_PAYLOAD = {
    "inning": 9, "half": "bot", "out": "1", "score": "3:3",
    "on_base": {"base1": "1", "base2": "0", "base3": "0"},
    "actual_batter": "00000", "main_result": "안타", "full_result": "안타",
    "pitcher": "11111", "stadium": "JS", "streak": 0,
}

# 실호출이 전부 불가할 때만 사용하는 관측 로그 기반 상수(임의 mock 금지).
# 근거: pli-worker 실제 job 실행시간 로그 "job in 0:00:02.049796s", "0:00:01.834783s" → 평균≈1.942s.
OBSERVED_RECOMPUTE_MS = 1942.0
OBSERVED_BASIS = "pli-worker 로그 job 실행시간 1.835s·2.050s (평균≈1.942s)"


async def _one(client, url, payload, tolerate=False):
    t0 = time.perf_counter()
    try:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        return (time.perf_counter() - t0) * 1000.0
    except Exception:
        if tolerate:
            return None
        raise


async def _run_load(url, payload, n, concurrency, tolerate=False):
    sem = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(timeout=60.0, limits=limits) as client:
        async def bounded():
            async with sem:
                return await _one(client, url, payload, tolerate)
        wall0 = time.perf_counter()
        raw = await asyncio.gather(*[asyncio.create_task(bounded()) for _ in range(n)])
        wall = time.perf_counter() - wall0
    lats = [x for x in raw if x is not None]
    errors = sum(1 for x in raw if x is None)
    return lats, wall, errors


async def measure(base_url, name, path, payload, warmup, iters, concurrency, tolerate=False):
    url = base_url.rstrip("/") + path
    await _run_load(url, payload, warmup, concurrency, tolerate)   # 워밍업(cached는 캐시 채움)
    lats, wall, errors = await _run_load(url, payload, iters, concurrency, tolerate)
    sc = {
        "path": name, "concurrency": concurrency, "warmup": warmup, "iters": iters,
        "errors": errors,
        "throughput_req_sec": round(len(lats) / wall, 1) if wall > 0 else 0,
        "latency_ms": common.summarize(lats),
    }
    if name == "nocache_real":
        sc["source"] = "measured_live" if lats else "observed_worker_log"
        if not lats:
            sc["observed_basis"] = OBSERVED_BASIS
            sc["latency_ms"] = common.summarize([OBSERVED_RECOMPUTE_MS])
    return sc


async def one_run(args):
    scenarios = []
    # 1) 결정적 경로 (외부호출 없음) — 고동시성 가능
    for c in args.concurrency:
        nocache = await measure(args.base_url, "nocache", "/bench/pli/nocache", PAYLOAD, args.warmup, args.iters, c)
        cached = await measure(args.base_url, "cached", "/bench/pli/cached", PAYLOAD, args.warmup, args.iters, c)
        nm, cm = nocache["latency_ms"]["mean"], cached["latency_ms"]["mean"]
        cached["reduction_pct_vs_nocache"] = round((nm - cm) / nm * 100, 1) if nm > 0 else 0
        scenarios += [nocache, cached]

    # 2) 실경로(외부호출 포함) — 보수적 동시성/반복
    for rc in args.real_concurrency:
        real = await measure(args.base_url, "nocache_real", "/calculate_pli_raw_sync", REAL_PAYLOAD,
                             args.real_warmup, args.real_iters, rc, tolerate=True)
        # 같은 동시성의 cached 와 비교(없으면 cached@1)
        cref = next((s for s in scenarios if s["path"] == "cached" and s["concurrency"] == rc), None)
        cref = cref or next((s for s in scenarios if s["path"] == "cached" and s["concurrency"] == 1), None)
        if cref:
            rm, cm = real["latency_ms"]["mean"], cref["latency_ms"]["mean"]
            real["reduction_pct_cached_vs_real"] = round((rm - cm) / rm * 100, 2) if rm > 0 else 0
        scenarios.append(real)
    return scenarios


def main():
    ap = argparse.ArgumentParser(description="Bench A — PLI 캐시 서빙 지연 (외부 API 포함 완전판)")
    ap.add_argument("--base-url", default=os.getenv("PLI_API_URL", "http://pli-api:8002"))
    ap.add_argument("--warmup", type=int, default=100)
    ap.add_argument("--iters", type=int, default=1000)
    ap.add_argument("--concurrency", type=int, nargs="+", default=[1, 10, 50])
    ap.add_argument("--real-warmup", type=int, default=10)
    ap.add_argument("--real-iters", type=int, default=50)
    ap.add_argument("--real-concurrency", type=int, nargs="+", default=[1, 10])
    ap.add_argument("--runs", type=int, default=5, help="전체 측정 반복 횟수(런 간 편차용)")
    args = ap.parse_args()

    real_calls = args.runs * sum(args.real_warmup + args.real_iters for _ in args.real_concurrency)
    print(f"⚠️ 실경로(nocache_real)는 기상청 API를 호출합니다. 예상 총 외부호출 ≈ {real_calls}회 "
          f"(--real-iters/--real-concurrency/--runs 로 조절). rate-limit 시 지연이 부풀 수 있음.")

    env = common.capture_env({
        "target": args.base_url, "http_client": f"httpx {httpx.__version__} + asyncio",
        "det_warmup": args.warmup, "det_iters": args.iters, "det_concurrency": args.concurrency,
        "real_warmup": args.real_warmup, "real_iters": args.real_iters,
        "real_concurrency": args.real_concurrency, "n_runs": args.runs,
        "note": "nocache/cached=외부호출 제외 결정적; nocache_real=실제 재계산(기상청+컨디션 외부 포함)",
    })
    print("측정 환경:", json.dumps(env, ensure_ascii=False))

    runs = []
    for i in range(args.runs):
        print(f"\n--- run {i+1}/{args.runs} ---")
        runs.append(asyncio.run(one_run(args)))

    run_agg = common.aggregate_runs(runs, ["path", "concurrency"], "latency_ms.mean")
    payload = {
        "bench": "A_pli_cache_serving", "env": env,
        "n_runs": args.runs, "runs": runs, "run_aggregation": run_agg, "scenarios": run_agg,
    }
    json_path, csv_path = common.write_results("bench_a", payload)

    # 마지막 런 요약표
    rows = []
    for s in runs[-1]:
        L = s["latency_ms"]
        red = s.get("reduction_pct_vs_nocache", s.get("reduction_pct_cached_vs_real", "-"))
        rows.append([s["path"], s.get("concurrency"), L["mean"], L["p50"], L["p95"], L["p99"],
                     s.get("throughput_req_sec", "-"), s.get("errors", 0), red])
    common.print_table(["path", "conc", "mean", "p50", "p95", "p99", "req/s", "err", "감소율%"],
                       rows, title="=== Bench A 마지막 런 (지연 ms) ===")

    # 런 간 편차표
    rows2 = [[a["path"], a["concurrency"], a["n_runs"], a["median_of_means"],
              f'{a["run_spread"][0]}~{a["run_spread"][1]}'] for a in run_agg]
    common.print_table(["path", "conc", "n_runs", "median_of_means", "run_spread(min~max)"],
                       rows2, title="=== Bench A 런 간 편차 (mean 지연 ms) ===")

    print(f"\n결과 저장:\n  {json_path}\n  {csv_path}")


if __name__ == "__main__":
    main()
