## 초기 클론 시 해야할 것들
### 1. 레포 클론
git clone https://github.com/ballrae/Back.git  
cd Back

### 2. 환경 변수 설정
cp .env.example .env
### → 일단 그대로 써도됨

### 3. Docker 실행 (백엔드 + DB 자동 시작)
docker-compose up --build
