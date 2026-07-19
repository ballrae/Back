# 성능 벤치마크 리포트

재현 가능한 실측으로 기존 성능 주장을 검증했다. **결론: 기존 주장(51% / 21.36ms / 10배 /
5경기 파티셔닝 병렬)은 재현되지 않아 전부 폐기**하고, 아래 실측값으로 대체한다.
수치는 모두 `bench/` 스크립트로 재현 가능하며 원시 결과는 `bench/results/`에 JSON/CSV로 저장된다.

## 측정 환경

| 항목 | 값 |
|---|---|
| 실행 | Docker (macOS 호스트, 컨테이너 내부 측정) |
| 아키텍처 | linux aarch64, CPU 4, RAM 7.67GB |
| Python | 3.11.15 |
| Redis | 7.4.9 |
| PostgreSQL | 17.5 |
| Kafka | confluentinc/cp-kafka 7.4.0 (client kafka-python 2.2.2, 단일 브로커) |
| 데이터 규모 | atbat 186,979행 / pitch 711,170행 |
| 반복 | 벤치별 --runs 2~3회, 각 런 워밍업 후 측정, p50/p95/p99 포함 |

---

## 벤치 A — PLI 캐시 서빙 지연

`docker compose exec web python bench/bench_a_pli.py --runs 3 --iters 500 --real-iters 30`

| path | conc | mean(ms) | p50 | p95 | p99 | 감소율% |
|---|---|---|---|---|---|---|
| nocache | 1 | 6.09 | 0.73 | 42.4 | 45.6 | — |
| cached | 1 | 7.93 | 0.90 | 42.9 | 45.7 | **-30.2** |
| nocache | 10 | 7.65 | 1.52 | 42.3 | 44.7 | — |
| cached | 10 | 9.01 | 1.46 | 42.5 | 44.2 | -17.8 |
| nocache_real | 1 | 9.35 | 1.00 | 42.5 | 43.4 | 15.2 |

**해석 (기존 "51% / 21.36ms" → 폐기):**
- 순수 PLI 계산은 이미 sub-ms(p50 0.7ms)라, **PLI 결과를 Redis에 캐싱하면 오히려 GET
  오버헤드로 더 느리다**(감소율 음수). 즉 "PLI 결과 캐시로 51% 단축"은 성립하지 않는다.
- 캐시의 실제 가치는 **PLI 결과가 아니라 외부 API 호출(기상청·컨디션)을 없애는 데** 있다.
  이번에 기상청은 시간당, 컨디션은 (타자,투수) 매치업 단위로 캐시하도록 바꿨고, 그 결과
  `nocache_real`(외부 포함 재계산)도 캐시 워밍 후 ~ms 수준으로 떨어진다.
- **엔드투엔드 실측(라이브 relay)**: 콜드 첫 로드 ~2.5초 → consumer 사전 워밍 후 **30~80ms**.
  즉 "실시간 서빙 지연"의 실제 개선은 *외부 API 캐시 + 사전 워밍*에서 나온다.

---

## 벤치 B — Redis GET vs PostgreSQL 직접 SELECT

`docker compose exec web python bench/bench_b_redis_vs_pg.py --runs 3 --iters 1000`
(동일 이닝 데이터: atbat 7 / pitch 40)

| path | mean(ms) | p50 | p95 | p99 |
|---|---|---|---|---|
| postgresql_select | 0.265 | 0.259 | 0.29 | 0.37 |
| redis_get | 0.112 | 0.111 | 0.124 | 0.13 |

- **배율: median 2.37배** (런 간 스프레드 2.35~2.73배, 안정적)

**해석 (기존 "10배" → 폐기):** 인덱스가 걸린 단일 이닝 조회에서 PostgreSQL도 0.26ms로
충분히 빠르다. Redis는 직렬화된 JSON 한 방 GET이라 0.11ms로 **약 2.4배** 빠르다. 10배는
재현되지 않는다. (조인·직렬화가 무거운 전체 경기 조회라면 격차가 더 벌어지지만, 공정한
동일-데이터 비교에서는 2.4배다.)

---

## 벤치 C — Kafka 파티셔닝 (처리량·순서·랙)

`docker compose exec web python bench/bench_c_kafka.py --mode compare --runs 2 --msgs-per-game 1000 --partitions 5 --consumers 5`
(+ `--mode badkey`)

| mode | key | 파티션 | 컨슈머 | consume msgs/s | 순서위반 |
|---|---|---|---|---|---|
| single | inning_label | 1 | 1 | 65,380 (median) | 0 |
| partitioned | **game_id** | 5 | 5 | 56,364 (median) | 0 |
| badkey | inning_label | 5 | 5 | 40,600 | **20** |

- 처리량 배율 partitioned/single = **0.86배** (파티셔닝이 오히려 약간 느림)

**해석 (기존 "5경기 파티셔닝 병렬 처리" → 폐기):**
- 워크로드(5,000 msg)가 작아 처리량 병목이 아니다. 단일 파티션도 초당 6.5만 건을 처리하며,
  이는 실제 KBO 트래픽(초당 수 건)을 압도한다. **파티셔닝은 이 규모에서 처리량 이득이 없고**,
  컨슈머 5개의 리밸런싱 오버헤드로 오히려 소폭 느리다.
- **정직하게 방어 가능한 사실**: (1) 단일 파티션 total-order로 이닝 순서가 보장된다(위반 0).
  (2) 만약 파티션을 늘린다면 **key를 game_id로 써야** 경기별 순서가 지켜진다 — 이닝 라벨을
  key로 두면(badkey) 같은 경기가 여러 파티션에 흩어져 **순서가 20건 깨진다**. 즉 "파티셔닝으로
  병렬 처리를 했다"가 아니라 "규모상 단일 파티션으로 순서 안전성을 택했고, 확장 시 올바른
  파티션 키를 규명했다"가 실측으로 뒷받침되는 서술이다.

---

## 기존 주장 vs 실측 (요약)

| 기존 주장 | 실측 | 판정 |
|---|---|---|
| Redis 캐싱으로 서빙 지연 51% 단축(평균 21.36ms) | PLI 결과 캐시는 순효과 음수. 실제 개선은 외부 API 캐시+사전워밍으로 relay 30~80ms | **폐기** — 재현 불가 |
| RDBMS 직접 조회 대비 10배 | 동일 이닝 조회에서 Redis가 **2.4배** | **폐기** — 실측 2.4배 |
| Kafka 파티셔닝으로 5경기 동시 순서 보장·병렬 처리 | 단일 파티션으로 순서 보장(위반 0). 파티셔닝 처리량 이득 없음(0.86배). game_id 키가 순서에 필수임은 실증 | **폐기** — 병렬 처리 이득 미검증 |

## 정직하게 쓸 수 있는 대체 서술 (실측 근거)

- "실시간 PLI 서빙에서 외부 API(기상청·컨디션) 호출을 시간당/매치업 단위로 캐시하고, 컨슈머가
  Redis 적재 시 PLI를 사전 계산하도록 바꿔 **이닝 조회 지연을 콜드 ~2.5초에서 워밍 후 30~80ms로**
  줄였다(라이브 실측)."
- "핫 리드에서 **Redis가 PostgreSQL 대비 약 2.4배 빠름**을 동일 데이터로 재현 측정했다."
- "이벤트 순서가 중요한 스트림에 대해 **단일 파티션 total-order로 순서를 보장**했고, 파티션 확장
  시 경기별 순서를 지키려면 **game_id를 파티션 키로 써야 함**을 벤치(대조군 20건 위반)로 규명했다."

## 재현 방법

```bash
docker compose up -d db redis pli-api web zookeeper kafka kafka-consumer
docker compose exec web python bench/bench_a_pli.py --runs 3
docker compose exec web python bench/bench_b_redis_vs_pg.py --runs 3
docker compose exec web python bench/bench_c_kafka.py --mode compare --runs 2
docker compose exec web python bench/bench_c_kafka.py --mode badkey --runs 1
```
원시 결과: `bench/results/*.json`, `*.csv`. 자세한 설명은 `bench/README.md`.
