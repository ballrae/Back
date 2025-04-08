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
꺼져있는 컨테이너 실행	docker-compose up -d	백그라운드(detached) 모드로 실행. --build 없이 실행  
실행 중인 컨테이너 중지	docker-compose down	실행된 모든 컨테이너 중지 + 네트워크 등 정리  
일시 정지	docker-compose stop	컨테이너는 남기고 실행만 중지  
일시 중지된 컨테이너 재실행	docker-compose start	stop으로 멈춘 걸 다시 실행    
