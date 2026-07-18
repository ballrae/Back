#!/usr/bin/env python3
"""
Bench C — Kafka 파티셔닝 처리량 · end-to-end 지연 · 컨슈머 랙 · 순서 보장 측정.

목적: 자소서 주장 ③("경기 ID를 key로 5개 경기 파티셔닝·순서 보장·병렬 처리")을
     실제 코드로 정직하게 검증하고, 개선 전/후를 나란히 비교한다.

모드:
  single       현재 구조 재현 — 1 파티션 + 이닝 라벨 key (game_id 파티셔닝 아님)
  badkey       N 파티션인데 key를 이닝 라벨로 두면 게임별 순서가 깨짐을 증명하는 대조군
  partitioned  개선안 — N 파티션 + game_id key + consumer group N개(병렬 소비)
  compare      single → partitioned 를 순차 실행하고 비교표 출력

측정 지표:
  - produce_throughput / consume_throughput (msgs/sec)
  - e2e latency: mean/p50/p95/p99/min/max (ms)  ← 메시지에 produce_ts 임베드
  - max_consumer_lag (produce와 consume 동시 진행 중 관측한 최대 backlog)
  - order_violations: 같은 game_id 안에서 seq 가 역행한 횟수 (0 이어야 순서 보장)

안전장치: 프로덕션 토픽('2026')/컨슈머그룹('db-save-group')은 건드리지 않는다.
         전용 벤치 토픽을 매 실행마다 생성/삭제하고, consumer group 도 실행마다 유니크.

실시간 API는 경기시간에만 동작하므로, 이 벤치는 라이브에 의존하지 않고
합성 메시지 스트림(또는 --replay 파일)을 재생해 부하를 재현한다.
"""
import os
import sys
import json
import time
import argparse
import threading
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
import common  # noqa: E402

from kafka import KafkaProducer, KafkaConsumer, TopicPartition  # noqa: E402
from kafka.admin import KafkaAdminClient, NewTopic  # noqa: E402
from kafka.errors import UnknownTopicOrPartitionError, TopicAlreadyExistsError  # noqa: E402

INNING_LABELS = [f"{i}회{h}" for i in range(1, 13) for h in ("초", "말")]


# --------------------------------------------------------------------------
# 메시지 스트림 생성 / 재생
# --------------------------------------------------------------------------
def build_messages(games: list[str], msgs_per_game: int) -> list[dict]:
    """5개 경기를 라운드로빈으로 인터리브. game_id별 seq는 단조증가."""
    msgs = []
    seq = {g: 0 for g in games}
    for _ in range(msgs_per_game):
        for g in games:
            seq[g] += 1
            msgs.append({
                "game_id": g,
                "label": INNING_LABELS[(seq[g] - 1) % len(INNING_LABELS)],
                "seq": seq[g],
            })
    return msgs


def load_replay(path: str) -> list[dict]:
    """JSONL 파일에서 메시지 재생 (각 줄에 game_id/label/seq 포함)."""
    msgs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                msgs.append(json.loads(line))
    return msgs


# --------------------------------------------------------------------------
# 토픽 관리
# --------------------------------------------------------------------------
def recreate_topic(bootstrap: str, topic: str, partitions: int) -> None:
    admin = KafkaAdminClient(bootstrap_servers=bootstrap)
    try:
        try:
            admin.delete_topics([topic])
        except UnknownTopicOrPartitionError:
            pass
        except Exception:
            pass
        # 삭제 반영 대기 후 생성 (재시도)
        last_err = None
        for _ in range(20):
            time.sleep(0.5)
            try:
                admin.create_topics([NewTopic(topic, num_partitions=partitions, replication_factor=1)])
                last_err = None
                break
            except TopicAlreadyExistsError as e:
                last_err = e
                # 아직 삭제가 안 끝남 → 다시 삭제 시도
                try:
                    admin.delete_topics([topic])
                except Exception:
                    pass
            except Exception as e:
                last_err = e
        if last_err:
            raise last_err
        # 파티션 메타데이터가 브로커에 퍼질 시간
        time.sleep(1.0)
    finally:
        admin.close()


def topic_partition_count(bootstrap: str, topic: str) -> int:
    c = KafkaConsumer(bootstrap_servers=bootstrap)
    try:
        parts = c.partitions_for_topic(topic) or set()
        return len(parts)
    finally:
        c.close()


# --------------------------------------------------------------------------
# 랙 모니터
# --------------------------------------------------------------------------
def sample_lag(bootstrap: str, topic: str, group: str) -> int | None:
    """group의 커밋 오프셋 대비 로그 끝 오프셋 합 = 총 backlog."""
    admin = KafkaAdminClient(bootstrap_servers=bootstrap)
    consumer = KafkaConsumer(bootstrap_servers=bootstrap)
    try:
        parts = consumer.partitions_for_topic(topic) or set()
        tps = [TopicPartition(topic, p) for p in parts]
        if not tps:
            return None
        end = consumer.end_offsets(tps)
        committed = admin.list_consumer_group_offsets(group)
        total = 0
        for tp in tps:
            e = end.get(tp, 0)
            c = committed.get(tp)
            c_off = c.offset if c else 0
            total += max(0, e - c_off)
        return total
    except Exception:
        return None
    finally:
        consumer.close()
        admin.close()


# --------------------------------------------------------------------------
# 프로듀서 / 컨슈머
# --------------------------------------------------------------------------
def run_producer(bootstrap: str, topic: str, mode: str, messages: list[dict]) -> float:
    producer = KafkaProducer(
        bootstrap_servers=bootstrap,
        value_serializer=lambda v: json.dumps(v).encode(),
        key_serializer=lambda k: k.encode() if k is not None else None,
        acks=1,
        linger_ms=5,
    )
    start = time.perf_counter()
    for m in messages:
        # 키 선택이 이 벤치의 핵심: 현재구조=이닝라벨, 개선=game_id
        key = m["game_id"] if mode == "partitioned" else m["label"]
        payload = dict(m)
        payload["produce_ts"] = time.time()
        producer.send(topic, key=key, value=payload)
    producer.flush()
    dur = time.perf_counter() - start
    producer.close()
    return dur


def run_consumers(bootstrap, topic, group, n_consumers, expected_total, timeout_s):
    """N개 컨슈머(동일 group)로 병렬 소비. e2e 지연·순서위반·처리량 수집."""
    result = {
        "lock": threading.Lock(),
        "latencies": [],
        "last_seq": {},
        "order_violations": 0,
        "count": 0,
        "first_ts": None,
        "last_ts": None,
    }
    stop = threading.Event()

    def consume_one():
        c = KafkaConsumer(
            topic,
            bootstrap_servers=bootstrap,
            group_id=group,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda x: json.loads(x.decode()),
            consumer_timeout_ms=1000,
        )
        try:
            while not stop.is_set():
                batch = c.poll(timeout_ms=300, max_records=500)
                if not batch:
                    continue
                now = time.time()
                for _tp, records in batch.items():
                    for rec in records:
                        v = rec.value
                        lat = (now - v["produce_ts"]) * 1000.0
                        with result["lock"]:
                            if result["first_ts"] is None:
                                result["first_ts"] = now
                            result["last_ts"] = now
                            result["latencies"].append(lat)
                            g, s = v["game_id"], v["seq"]
                            last = result["last_seq"].get(g)
                            if last is not None and s <= last:
                                result["order_violations"] += 1
                            result["last_seq"][g] = s
                            result["count"] += 1
                            if result["count"] >= expected_total:
                                stop.set()
        finally:
            c.close()

    threads = [threading.Thread(target=consume_one, daemon=True) for _ in range(n_consumers)]
    for t in threads:
        t.start()
    return result, stop, threads


# --------------------------------------------------------------------------
# 한 시나리오 실행
# --------------------------------------------------------------------------
def run_scenario(bootstrap, mode, messages, partitions, consumers, msg_timeout_s):
    ts = datetime.now().strftime("%H%M%S")
    topic = f"benchc_{mode}_{ts}"
    group = f"benchc-{mode}-{ts}"
    n_parts = 1 if mode == "single" else partitions
    n_cons = 1 if mode == "single" else consumers

    print(f"\n[{mode}] 토픽={topic} 파티션={n_parts} 컨슈머={n_cons} 메시지={len(messages)}")
    recreate_topic(bootstrap, topic, n_parts)
    actual_parts = topic_partition_count(bootstrap, topic)

    expected = len(messages)
    # 컨슈머 먼저 구독 시작 (produce와 consume 동시 진행 → e2e·lag 실측)
    result, stop, threads = run_consumers(bootstrap, topic, group, n_cons, expected, msg_timeout_s)
    time.sleep(1.0)  # 컨슈머 파티션 할당 대기

    # 랙 모니터
    max_lag = {"v": 0}
    lag_stop = threading.Event()

    def lag_loop():
        while not lag_stop.is_set():
            l = sample_lag(bootstrap, topic, group)
            if l is not None and l > max_lag["v"]:
                max_lag["v"] = l
            time.sleep(0.1)

    lag_thread = threading.Thread(target=lag_loop, daemon=True)
    lag_thread.start()

    produce_dur = run_producer(bootstrap, topic, mode, messages)

    # 소비 완료 대기
    deadline = time.time() + msg_timeout_s
    while not stop.is_set() and time.time() < deadline:
        time.sleep(0.2)
    stop.set()
    lag_stop.set()
    for t in threads:
        t.join(timeout=3)
    lag_thread.join(timeout=1)

    with result["lock"]:
        consumed = result["count"]
        lat = list(result["latencies"])
        violations = result["order_violations"]
        first_ts, last_ts = result["first_ts"], result["last_ts"]

    consume_dur = (last_ts - first_ts) if (first_ts and last_ts and last_ts > first_ts) else produce_dur
    produce_tps = round(expected / produce_dur, 1) if produce_dur > 0 else 0
    consume_tps = round(consumed / consume_dur, 1) if consume_dur > 0 else 0

    scenario = {
        "mode": mode,
        "key_field": "game_id" if mode == "partitioned" else "inning_label",
        "partitions": actual_parts,
        "consumers": n_cons,
        "messages_produced": expected,
        "messages_consumed": consumed,
        "produce_throughput_msgs_sec": produce_tps,
        "consume_throughput_msgs_sec": consume_tps,
        "e2e_latency_ms": common.summarize(lat),
        "max_consumer_lag": max_lag["v"],
        "order_violations": violations,
        "order_guaranteed": violations == 0,
    }

    # 정리: 토픽 삭제
    try:
        admin = KafkaAdminClient(bootstrap_servers=bootstrap)
        admin.delete_topics([topic])
        admin.close()
    except Exception:
        pass

    return scenario


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Bench C — Kafka 파티셔닝 측정")
    ap.add_argument("--mode", choices=["single", "badkey", "partitioned", "compare"], default="compare")
    ap.add_argument("--bootstrap", default=os.getenv("KAFKA_BROKERS", "kafka:9092"))
    ap.add_argument("--games", type=int, default=5)
    ap.add_argument("--msgs-per-game", type=int, default=2000)
    ap.add_argument("--partitions", type=int, default=5)
    ap.add_argument("--consumers", type=int, default=5)
    ap.add_argument("--timeout", type=int, default=60, help="소비 완료 대기 최대 초")
    ap.add_argument("--replay", default=None, help="JSONL 메시지 재생 파일(선택)")
    ap.add_argument("--runs", type=int, default=5, help="전체 측정 반복 횟수(런 간 편차용)")
    args = ap.parse_args()

    games = [f"20260701G{i:02d}0" for i in range(args.games)]
    if args.replay:
        messages = load_replay(args.replay)
        print(f"replay: {args.replay} 에서 {len(messages)}개 메시지 로드")
    else:
        messages = build_messages(games, args.msgs_per_game)

    env = common.capture_env({
        "kafka_bootstrap": args.bootstrap,
        "kafka_image": "confluentinc/cp-kafka:7.4.0 (compose 기준)",
        "kafka_client": "kafka-python 2.2.2",
        "games": args.games,
        "msgs_per_game": args.msgs_per_game if not args.replay else None,
        "total_messages": len(messages),
        "requested_partitions": args.partitions,
        "requested_consumers": args.consumers,
    })
    print("측정 환경:", json.dumps(env, ensure_ascii=False))

    modes = ["single", "partitioned"] if args.mode == "compare" else [args.mode]
    runs = []
    for i in range(args.runs):
        print(f"\n=== run {i+1}/{args.runs} ===")
        scenarios = []
        for m in modes:
            scenarios.append(
                run_scenario(args.bootstrap, m, messages, args.partitions, args.consumers, args.timeout)
            )
        runs.append(scenarios)

    run_agg = common.aggregate_runs(runs, ["mode"], "consume_throughput_msgs_sec")
    payload = {
        "bench": "C_kafka_partitioning", "env": env,
        "n_runs": args.runs, "runs": runs, "run_aggregation": run_agg,
        "scenarios": run_agg,
    }
    json_path, csv_path = common.write_results("bench_c", payload)

    # 마지막 런 요약표
    headers = ["mode", "key", "part", "cons", "prod/s", "cons/s", "p50", "p95", "p99", "maxlag", "order_viol"]
    rows = []
    for s in runs[-1]:
        e = s["e2e_latency_ms"]
        rows.append([
            s["mode"], s["key_field"], s["partitions"], s["consumers"],
            s["produce_throughput_msgs_sec"], s["consume_throughput_msgs_sec"],
            e["p50"], e["p95"], e["p99"], s["max_consumer_lag"], s["order_violations"],
        ])
    common.print_table(headers, rows, title="=== Bench C 마지막 런 (지연 ms) ===")

    # 런 간 편차표 (consume 처리량)
    rows2 = [[a["mode"], a["n_runs"], a["median_of_means"], f'{a["run_spread"][0]}~{a["run_spread"][1]}']
             for a in run_agg]
    common.print_table(["mode", "n_runs", "median_of_means", "run_spread(min~max)"],
                       rows2, title="=== Bench C 런 간 편차 (consume msgs/sec) ===")

    if len(modes) == 2:
        agg = {a["mode"]: a["median_of_means"] for a in run_agg}
        base_tps = agg.get(modes[0]) or 1
        speedup = round((agg.get(modes[1]) or 0) / base_tps, 2)
        print(f"\n처리량 배율(consume, 런 median): {modes[1]}/{modes[0]} = {speedup}x")
        last = {s["mode"]: s for s in runs[-1]}
        print(f"순서 보장(마지막 런): "
              f"{modes[0]}={last[modes[0]]['order_guaranteed']} / "
              f"{modes[1]}={last[modes[1]]['order_guaranteed']}")

    print(f"\n결과 저장:\n  {json_path}\n  {csv_path}")


if __name__ == "__main__":
    main()
