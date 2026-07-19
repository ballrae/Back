# Ballrae Backend

KBO 프로야구 **실시간 문자중계 · 기록 · 커뮤니티** 서비스의 백엔드.
Django(REST + Channels) 위에서 Kafka·Redis·Celery로 경기 데이터를 실시간 수집·중계하고,
타석별 **승부처 지표(LI/PLI)** 와 선수 기록을 함께 서빙한다.

> **개발 상태**
> - 실시간 중계 · 기록 · 커뮤니티 API: 동작
> - **PLI(승부처 지표) 기능: 개선중** — 아래 [PLI (개선중)](#pli-승부처-지표-개선중) 참고

## Tech Stack

### Backend
![Python](https://img.shields.io/badge/python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Django](https://img.shields.io/badge/django-%23092E20.svg?style=for-the-badge&logo=django&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)

### Data & DB
![Apache Kafka](https://img.shields.io/badge/Apache%20Kafka-000?style=for-the-badge&logo=apachekafka)
![Redis](https://img.shields.io/badge/redis-%23DD0031.svg?style=for-the-badge&logo=redis&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/postgres-%23316192.svg?style=for-the-badge&logo=postgresql&logoColor=white)

### DevOps & Infra
![AWS](https://img.shields.io/badge/AWS-%23FF9900.svg?style=for-the-badge&logo=amazon-aws&logoColor=white)
![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/github%20actions-%232671E5.svg?style=for-the-badge&logo=githubactions&logoColor=white)

---

## 아키텍처

`docker-compose` 로 아래 서비스가 함께 뜬다.

| 서비스 | 역할 |
|---|---|
| `web` | Django(REST API + Channels/ASGI). 메인 백엔드 |
| `db` | PostgreSQL. 경기·타석·선수·유저 데이터 |
| `redis` | 캐시 / Channels 레이어 / RQ·Celery 브로커 |
| `kafka` + `zookeeper` | 실시간 중계 이벤트 스트림 |
| `kafka-producer` / `kafka-consumer` | 경기 원본 수집 → 파싱·적재 |
| `pli-api` | 타석 LI/PLI 계산 (FastAPI). **개선중** |
| `pli-worker` | PLI 비동기 계산 워커(RQ) |
| `hate-filter-api` | 댓글 혐오표현 필터 (FastAPI) |

```
경기 원본 ──> kafka-producer ──> Kafka ──> kafka-consumer ──> PostgreSQL
                                                  │
                                    web(Django) ──┼── REST API
                                                  └── Channels(WS) 실시간 중계
                                                       │
                                                 pli-api / hate-filter-api
```

## 앱 · API

Django 앱은 `ballrae_backend/` 아래에 있고, 라우트 프리픽스는 `ballrae_backend/urls.py` 기준.

| 앱 | 프리픽스 | 주요 엔드포인트 |
|---|---|---|
| `users` | `/api/users/` | 카카오 로그인, 내 정보, 마이팀, 토큰 리프레시 |
| `teams` | `/api/teams/` | 구단 목록 |
| `posts` | `/api/posts/` | 구단별 게시글·댓글·좋아요 |
| `games` | `/api/games/` | 경기 목록(`gamelist/<date>`), 이닝별 실시간 중계(`<game_id>/relay/<inning>/`) |
| `players`| `/api/players/` | 타자·투수 기록, 실시간 라인업, 선수 검색 |
| `streaming` | — | Kafka producer/consumer, Channels consumer (경기 실시간 파이프라인) |

## 실시간 중계 파이프라인

`ballrae_backend/streaming/` 이 담당한다.
- `producer.py` : 경기 원본 데이터를 Kafka로 발행
- `consumer.py` : Kafka 소비 → 파싱 → DB 적재 → Channels 로 브로드캐스트
- `redis_client.py` : 캐시 / 실시간 상태 공유
- 스케줄링은 `dags/producer_dag.py` (Airflow) 및 Celery(`celery.py`) 사용

---

## PLI (승부처 지표, 개선중)

타석마다 "지금이 얼마나 승부처인가"를 나타내는 지표. **Leverage Index(LI)** 기반으로 재정의 중이며,
계산은 별도 서비스 `pli-api/` (FastAPI + RQ 워커)에서 수행하고 `games` 중계 응답(`pli_data`)에 실려 나간다.

- 상세 설계·검증·재학습 방법: [`pli-api/README.md`](pli-api/README.md)
- 승률(WP) 모델 학습 스크립트: [`train_wp_model.py`](train_wp_model.py) → `data/wp_model.json`

**개선중인 부분**
- 압박(Pressure) 가중치의 실질 기여가 아직 작음(컨디션·날씨 데이터 미충족 시 `pli ≈ li`).
- WP 모델은 로지스틱 기반. 필요 시 GBM 등으로 교체 예정(피처 함수 정의만 동일 유지).
- 값 스케일·오탐(blowout 국면) 튜닝 진행 중.

성능 실측은 [`BENCHMARK.md`](BENCHMARK.md) 참고.

---

## 초기 세팅

### 1. 레포 클론
```bash
git clone https://github.com/ballrae/Back.git
cd Back
```

### 2. 환경 변수 설정
로컬에서는 `.env` 파일을 사용한다. `.env.example` 을 복제해서 값을 채운다.
```bash
cp .env.example .env
```

### 3. Docker 실행 (백엔드 + DB 자동 시작)
**첫 시작 (이미지 빌드 포함)**
```bash
docker-compose up --build
```

**이후 사용**

| 명령 | 설명 |
|---|---|
| `docker-compose up -d` | 백그라운드(detached)로 실행 (`--build` 없이) |
| `docker-compose down` | 모든 컨테이너 중지 + 네트워크 정리 |
| `docker-compose stop` | 컨테이너는 남기고 실행만 중지 |
| `docker-compose start` | `stop` 으로 멈춘 컨테이너 다시 실행 |

### 요구 사항
- Docker / docker-compose
- Python 3.11 (컨테이너 기준)

---

## 배포

`.github/workflows/cicd_demo.yaml` — `main` push 시 ECR 빌드 후 EC2 배포.
> 현재 EC2 미사용으로 **워크플로 비활성화 상태**. 재개하려면
> `gh workflow enable "Deploy via ECR to EC2"`.
