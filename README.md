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

## 초기 클론 시 해야할 것들
### 1. 레포 클론
git clone https://github.com/ballrae/Back.git  
cd Back

### 2. 환경 변수 설정
**본인 로컬에서는 .env 파일 사용해야하므로 .env.example 파일을 복제해주는 것**
cp .env.example .env


### 3. Docker 실행 (백엔드 + DB 자동 시작)
**첫시작**
docker-compose up --build  

**사용**  
꺼져있는 컨테이너 실행	: docker-compose up -d	백그라운드(detached) 모드로 실행. --build 없이 실행  
실행 중인 컨테이너 중지	: docker-compose down	실행된 모든 컨테이너 중지 + 네트워크 등 정리  
일시 정지 :	docker-compose stop	컨테이너는 남기고 실행만 중지  
일시 중지된 컨테이너 재실행 :	docker-compose start	stop으로 멈춘 걸 다시 실행    
