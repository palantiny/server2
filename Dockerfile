# Palantiny Chatbot Server - Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성 (asyncpg 빌드용)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# DB 마이그레이션은 앱 시작 시 또는 별도 init 스크립트에서 수행
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
