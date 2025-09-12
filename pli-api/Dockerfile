# 사용할 파이썬 버전을 지정합니다.
FROM python:3.10-slim

# 컨테이너 내에서 작업할 디렉토리를 설정합니다.
WORKDIR /app
# PYTHONPATH 환경 변수를 설정하여 앱 모듈을 쉽게 찾을 수 있게 합니다.
ENV PYTHONPATH=/app

# 시스템 라이브러리 업데이트 및 설치
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

# 파이썬 의존성 파일(requirements.txt)을 복사하고 설치합니다.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# 애플리케이션 코드를 /app 디렉토리로 복사합니다.
COPY app/ . 

# 데이터 파일을 /app 디렉토리로 복사합니다.
# 이 명령어가 에러를 냈던 바로 그 부분입니다.
# 이번에는 Dockerfile이 아니라 docker-compose.yml에서 volume으로 연결하는 게 더 좋습니다.
# 하지만 당장 에러를 해결하기 위해 Dockerfile에 그대로 둡니다.
# 나중에 개발 환경을 위해 volumes로 바꾸면 됩니다.
# COPY ../data/ /app/data/

# Uvicorn을 사용해 FastAPI 앱을 실행합니다.
CMD ["uvicorn", "pli_api:app", "--host", "0.0.0.0", "--port", "8002", "--reload"]