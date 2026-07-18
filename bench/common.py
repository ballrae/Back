"""
벤치 공통 유틸: 측정 환경 캡처, percentile 계산, 결과 저장(JSON/CSV), 콘솔 표 출력.
외부 의존성 없이 표준 라이브러리만 사용 (psutil 등 불필요).
"""
import os
import csv
import json
import time
import platform
import statistics
from datetime import datetime

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")


def _mem_total_gb():
    """리눅스 컨테이너 기준 물리 메모리(GB). 실패 시 None."""
    try:
        return round(
            os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024 ** 3), 2
        )
    except Exception:
        return None


def capture_env(extra: dict | None = None) -> dict:
    """CPU/RAM/도커여부/버전 등 측정 환경을 기록."""
    env = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "mem_total_gb": _mem_total_gb(),
        "in_docker": os.path.exists("/.dockerenv"),
    }
    if extra:
        env.update(extra)
    return env


def summarize(latencies_ms: list[float]) -> dict:
    """지연 리스트 → mean/p50/p95/p99/min/max/count (ms)."""
    if not latencies_ms:
        return {"count": 0, "mean": 0, "p50": 0, "p95": 0, "p99": 0, "min": 0, "max": 0}
    s = sorted(latencies_ms)
    n = len(s)

    def pct(p):
        # nearest-rank
        idx = min(n - 1, max(0, int(round(p / 100 * n)) - 1))
        return round(s[idx], 3)

    return {
        "count": n,
        "mean": round(statistics.fmean(s), 3),
        "p50": pct(50),
        "p95": pct(95),
        "p99": pct(99),
        "min": round(s[0], 3),
        "max": round(s[-1], 3),
    }


def write_results(name: str, payload: dict) -> tuple[str, str]:
    """results/{name}_{ts}.json 과 .csv 저장. csv는 scenario별 1행."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = os.path.join(RESULTS_DIR, f"{name}_{ts}")
    json_path = base + ".json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    csv_path = base + ".csv"
    rows = payload.get("scenarios", [])
    if rows:
        # 중첩 dict를 flatten
        flat_rows = [_flatten(r) for r in rows]
        keys = []
        for r in flat_rows:
            for k in r:
                if k not in keys:
                    keys.append(k)
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(flat_rows)
    return json_path, csv_path


def _flatten(d: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, prefix=f"{key}."))
        else:
            out[key] = v
    return out


def _get_dotted(d: dict, path: str):
    cur = d
    for p in path.split("."):
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur


def aggregate_runs(runs: list[list[dict]], key_fields: list[str], value_path: str) -> list[dict]:
    """
    여러 번 실행(run) 결과를 시나리오별로 묶어 런 간 편차를 계산.
    - runs: 실행별 scenario 리스트의 리스트
    - key_fields: 시나리오를 식별하는 키(예: ["path","concurrency"])
    - value_path: 각 실행에서 집계할 대표값 경로(예: "latency_ms.mean")
    반환: 시나리오별 {키.., n_runs, median_of_means, run_spread:[min,max], per_run:[...]}
    """
    from collections import OrderedDict
    groups: "OrderedDict[tuple, dict]" = OrderedDict()
    for run in runs:
        for sc in run:
            key = tuple(str(sc.get(f)) for f in key_fields)
            val = _get_dotted(sc, value_path)
            if val is None:
                continue
            if key not in groups:
                groups[key] = {"key": {f: sc.get(f) for f in key_fields}, "values": []}
            groups[key]["values"].append(val)

    out = []
    for g in groups.values():
        vals = g["values"]
        if not vals:
            continue
        out.append({
            **g["key"],
            "metric": value_path,
            "n_runs": len(vals),
            "median_of_means": round(statistics.median(vals), 3),
            "run_spread": [round(min(vals), 3), round(max(vals), 3)],
            "per_run": [round(v, 3) for v in vals],
        })
    return out


def print_table(headers: list[str], rows: list[list], title: str = "") -> None:
    """간단한 고정폭 콘솔 표."""
    if title:
        print(f"\n{title}")
    cols = [headers] + [[str(c) for c in r] for r in rows]
    widths = [max(len(row[i]) for row in cols) for i in range(len(headers))]
    line = "-+-".join("-" * w for w in widths)
    print(" | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print(line)
    for r in rows:
        print(" | ".join(str(c).ljust(widths[i]) for i, c in enumerate(r)))
