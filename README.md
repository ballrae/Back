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
