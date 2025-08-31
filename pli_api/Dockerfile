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
COPY data/ /app/data/

# Uvicorn을 사용해 FastAPI 앱을 실행합니다.
# 'main'은 모듈 이름, 'app'은 FastAPI 인스턴스 이름입니다.
# app 폴더를 통째로 복사했으므로 'app.pli_api'가 아니라 'pli_api'가 맞을 수 있습니다.
# 파일 이름이 pli_api.py라면 CMD ["uvicorn", "pli_api:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "1"] 로 변경하는게 더 정확합니다.
CMD ["uvicorn", "pli_api:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "1"]