# bench/ — 재현 가능한 성능 벤치마크

이 디렉토리는 자소서·면접에서 **방어 가능한(재현 가능한)** 성능 수치를 만들기 위한
측정 스크립트다. 수치를 임의로 만들지 않고 실제 코드/인프라로 측정하며, 측정 불가한
항목은 "측정 불가"로 명시한다.

검증 대상(기존 주장):
1. Redis 캐싱으로 서빙 지연 51% 단축(평균 21.36ms) — **벤치 A**
2. RDBMS 직접 조회 대비 10배 이상 빠름 — **벤치 B**
3. Kafka 파티셔닝으로 5개 경기 동시 순서 보장·병렬 처리 — **벤치 C** ✅ 구현됨

> 상태: 벤치 A / B / C 모두 구현 완료. 실측 후 최종 비교표 작성만 남음.

---

## 부하 도구 선택 이유

- **Kafka(벤치 C)**: `kafka-python`(이미 `requirements.txt`에 `kafka-python==2.2.2`)을 사용.
  프로덕션 producer/consumer와 **동일한 클라이언트**로 측정해야 결과가 실제 코드 경로를
  대변한다. 새 의존성 추가 없음.
- **HTTP(벤치 A)**: 저장소가 이미 `httpx`에 의존하므로 **httpx + asyncio** 커스텀
  스크립트로 동시성(10/50)을 제어할 예정. locust/k6는 별도 설치·별도 언어(k6=JS)라
  이 스택엔 오버헤드. (벤치 A 구현 시 추가)
- **percentile**: 모든 벤치가 mean뿐 아니라 p50/p95/p99를 반드시 포함
  (`common.summarize`).

---

## 벤치 C — Kafka 파티셔닝 (처리량·순서·랙)

### 무엇을, 왜

주장 ③을 정직하게 검증한다. **현재 코드는 game_id로 파티셔닝하지 않는다** —
메시지 key가 이닝 라벨(`"1회초"`)이고 토픽은 기본 1파티션이다
([producer.py `produce()`](../ballrae_backend/streaming/producer.py#L56),
[consumer.py](../ballrae_backend/streaming/consumer.py#L100)).
그래서 3개 모드를 측정해 "문제 → 원인 → 개선"을 실측으로 보여준다.

| 모드 | 파티션 | key | 의미 |
|---|---|---|---|
| `single` | 1 | 이닝 라벨 | **현재 구조**. 단일 파티션 total-order라 순서는 지켜지나 병렬 없음 |
| `badkey` | N | 이닝 라벨 | N파티션이어도 **key가 틀리면 게임별 순서가 깨짐**을 증명하는 대조군 |
| `partitioned` | N | **game_id** | **개선안**. 게임별 순서 보장 + consumer group N개 병렬 소비 |

측정 지표: produce/consume 처리량(msgs/sec), e2e 지연(mean/p50/p95/p99/min/max),
최대 컨슈머 랙, **게임별 순서 위반 수**(같은 game_id 안에서 seq 역행 횟수).

- 라이브 API는 경기시간(18:30~21:30)에만 동작하므로, 이 벤치는 **합성 메시지 스트림**을
  재생해 부하를 재현한다(라이브 불필요). `--replay <JSONL>`로 캡처 로그 재생도 가능.
- **프로덕션 토픽(`2026`)·컨슈머그룹(`db-save-group`)은 건드리지 않는다** —
  매 실행마다 전용 벤치 토픽(`benchc_*`)을 생성/삭제하고 group도 유니크.

### 실행

Kafka·Zookeeper가 떠 있어야 한다(다른 서비스 불필요):

```bash
cd /Users/yubin/Desktop/2025/dev/Back
docker compose up -d zookeeper kafka

# 2버전 비교 (single vs partitioned) — 기본
docker compose exec web python bench/bench_c_kafka.py --mode compare

# 개별 모드
docker compose exec web python bench/bench_c_kafka.py --mode single
docker compose exec web python bench/bench_c_kafka.py --mode badkey       # 순서 깨짐 증명
docker compose exec web python bench/bench_c_kafka.py --mode partitioned

# 파라미터
docker compose exec web python bench/bench_c_kafka.py --mode compare \
  --games 5 --msgs-per-game 2000 --partitions 5 --consumers 5 --timeout 60
```

`web` 컨테이너에서 실행하는 이유: `kafka-python`이 설치돼 있고 브로커를 내부
네트워크 `kafka:9092`로 접근할 수 있기 때문. 호스트에서 직접 돌리려면
`--bootstrap localhost:9092`.

### 결과

- 콘솔에 요약표 출력.
- `bench/results/bench_c_<timestamp>.json` (전체) + `.csv`(시나리오별 1행) 저장.
- 3회 반복해 편차를 확인하는 것을 권장(안정성 근거).

### 해석 가이드 (주장 ③ 대조)

- `single`의 `order_violations == 0` → 순서는 보장되지만 **단일 파티션 total-order**
  덕분이지 game_id 파티셔닝 때문이 아님.
- `badkey`의 `order_violations > 0` → N파티션에서 **잘못된 key면 게임별 순서가 깨짐**.
- `partitioned`의 `order_violations == 0` + 더 높은 consume 처리량 →
  **game_id key로 순서 보장 + 병렬 처리**를 동시에 달성(개선 효과).

---

## 벤치 A — PLI 서빙 지연 (캐시 효과)

주장 ①("Redis 캐싱으로 서빙 지연 51% 단축, 평균 21.36ms") 검증.

- **nocache**: `POST /bench/pli/nocache` — 매 요청 재계산
- **cached**: `POST /bench/pli/cached` — Redis 캐시 히트(워밍업으로 캐시 채운 뒤 측정)
- 동일 입력, 워밍업 100 + 1,000회, **순차(1)와 동시(10, 50)** 모두. p50/p95/p99 포함.
- 감소율 = (nocache_mean − cached_mean) / nocache_mean.
- **정직성 주석**: 벤치 엔드포인트는 외부(기상청/컨디션) 호출을 **제외한 결정적 계산**이다.
  실제 라이브 재계산은 그 외부 호출까지 포함해 훨씬 비싸므로(관측상 타석당 ~2초),
  여기 감소율은 **캐시 이득의 보수적 하한**이다. 캐시 전략은 실제
  [`services._fetch_single_pli`](../ballrae_backend/games/services.py#L150)와 동일(요청 해시 → Redis).
- 도구: **httpx + asyncio**(저장소 기존 의존성, 동시성 정밀 제어, 설치 불필요).

```bash
docker compose up -d redis pli-api            # web 컨테이너에서 실행
docker compose exec web python bench/bench_a_pli.py                 # 동시성 1/10/50
docker compose exec web python bench/bench_a_pli.py --concurrency 1 10 50 100 --iters 2000
```

## 벤치 B — Redis GET vs PostgreSQL 직접 SELECT

주장 ②("RDBMS 직접 조회 대비 10배 이상") 검증.

- 같은 데이터(실제 한 이닝의 atbats+pitches)를 **psycopg2 직접 SELECT** vs **Redis GET+json**.
- 워밍업 100 + 1,000회, 배율 = pg_mean / redis_mean. p50/p95/p99 포함.
- **in-process(순수 psycopg2+redis)** 로 측정 — Django ORM/DEBUG 오버헤드 배제해
  "저장소 조회 자체"를 공정 비교. 커넥션 1회 재사용(현실적 풀링).
- 사전 조건: DB에 경기 기록 적재돼 있어야 함(`games_atbat` ≥ 한 이닝).

```bash
docker compose up -d db redis                 # web 컨테이너에서 실행
docker compose exec web python bench/bench_b_redis_vs_pg.py
docker compose exec web python bench/bench_b_redis_vs_pg.py --iters 2000
```

## 반복 집계 모드 (`--runs`, 기본 5)

세 벤치 모두 `--runs N`으로 **전체 측정을 N회 연속 실행**하고, 각 실행의 대표값(A/B=mean 지연,
C=consume 처리량)을 모아 **런 간 median과 최소~최대 스프레드**를 계산한다. 이는 런 내부의
p50/p95/p99와는 **별개 지표**(런 사이 안정성)다.

- 결과 JSON: `n_runs`, `runs`(원시 런별), `run_aggregation`(시나리오별 `median_of_means`·`run_spread`·`per_run`).
- 콘솔: "런 간 편차" 표를 별도로 출력.

```bash
docker compose exec web python bench/bench_a_pli.py --runs 5
docker compose exec web python bench/bench_b_redis_vs_pg.py --runs 5
docker compose exec web python bench/bench_c_kafka.py --mode compare --runs 5
```

## 벤치 A `nocache_real` — 캐시의 진짜 가치 (외부 API 포함 완전판)

`nocache`/`cached`는 외부호출 제외 결정적 계산이라 캐시 이득이 작게 나온다(계산 자체가 원래 빠름).
그래서 **실제 프로덕션 재계산 경로**(`POST /calculate_pli_raw_sync`, 기상청+컨디션 외부호출 포함)를
정식 측정 경로로 둔다 — 워밍업+반복+동시성으로 **퍼센타일까지** 산출.

- 파라미터: `--real-warmup`(기본 10) `--real-iters`(기본 50) `--real-concurrency`(기본 1 10).
- 캐시 히트(같은 동시성 cached) 대비 감소율 = `reduction_pct_cached_vs_real` → "캐시의 진짜 가치".
- ⚠️ **외부 API 주의**: 매 호출이 기상청(정부) API를 때린다. 실행 시 예상 총 외부호출 수를 경고로 찍는다.
  고동시성×대량 반복은 rate-limit·차단 위험(측정 오염) → 기본값은 보수적. 필요시 플래그로 확대.
  **재계산 경로가 외부 API 때문에 고동시성 확장이 불가한 것 자체가 "캐시가 필수인 이유"**다.
- **정직성**: 실호출이 전부 실패하면 **관측 로그 기반 상수**로 대체(임의 mock 금지).
  근거: pli-worker 실제 job 실행시간 로그 `1.835s`·`2.050s` → 평균 ≈ **1.942s**.

```bash
# 완전판 (외부 포함) 기본
docker compose exec web python bench/bench_a_pli.py --runs 5
# 실경로를 더 크게(외부호출 늘어남 주의)
docker compose exec web python bench/bench_a_pli.py --real-iters 100 --real-concurrency 1 10 50
```

## 판정 정책 (재현 실패 = 폐기 확정)

3~5회 반복해도 기존 주장(**51% / 21.36ms / 10배**)이 재현되지 않으면 **"폐기 확정"으로 기록**한다.
반복의 목적은 수치를 되살리는 게 아니라 **안정성·정직성 근거 확보**다. 실측값을 정답으로 채택하고,
기존 값은 "재현 불가 — 폐기"로 비교표에 명시한다.

## 최종 비교표 (실측 후 작성)

세 벤치를 각각 **3회 반복**(편차 확인)한 뒤, 기존 주장과 실측을 나란히:

| 주장 | 기존 값 | 실측 값 | 판정/설명 |
|---|---|---|---|
| ① 캐시 서빙 지연 단축 | 51% / 21.36ms | (벤치 A) | |
| ② RDBMS 대비 배율 | 10배 | (벤치 B) | |
| ③ Kafka 파티셔닝 | 5경기 순서·병렬 | (벤치 C) | 현재구조는 미구현 → 개선 후 실측 |

차이가 있으면 실측값을 정답으로 채택하고 원인(측정 정의 차이·환경 차이 등)을 명시한다.

---

## 측정 환경 기록

`common.capture_env()`가 실행 시각·platform·python·CPU 수·RAM·Docker 여부와
각 벤치별 설정(메시지 규모, 파티션/컨슈머 수, 클라이언트 버전 등)을 결과 JSON에
함께 저장한다. 인프라 버전(Kafka `confluentinc/cp-kafka:7.4.0`,
Postgres/Redis 등)은 `docker-compose.yml` 기준.

---

## TODO (다음 단계)

- [x] 벤치 A — PLI 서빙 지연(캐시 vs 비캐시), 순차 + 동시(10/50), httpx+asyncio
- [x] 벤치 B — Redis GET vs PostgreSQL SELECT 배율
- [x] 벤치 C — Kafka 파티셔닝(현재/개선 2버전)
- [ ] 3회 반복 실측 + 편차 기록
- [ ] 최종 비교표 — 실측값 vs 기존 주장(51%/21.36ms/10배)
