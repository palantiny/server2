# Palantiny (팔란티니) - 한약재 유통 B2B2C 챗봇 서버

FastAPI 기반의 한약재 유통 자동화 챗봇 서버입니다.

## 기술 스택

- Python, FastAPI, WebSockets
- Redis (Queue, Pub/Sub)
- PostgreSQL (SQLAlchemy async)
- OpenAI (선택, Mock 모드 지원)

## 빠른 시작

### 1. Docker Compose로 실행

```bash
# PostgreSQL, Redis, App 컨테이너 기동
docker-compose up -d

# 시드 데이터 삽입 (App 컨테이너 내)
docker-compose exec app python -m scripts.seed_data
```

### 2. 로컬 개발

```bash
# .env 설정
cp .env.example .env

# PostgreSQL, Redis만 Docker로 실행
docker-compose up -d postgres redis

# 가상환경 및 의존성
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt

# 시드 데이터
python -m scripts.seed_data

# 서버 실행
uvicorn app.main:app --reload --port 8000
```

## API 엔드포인트

### 인증

```
POST /api/v1/auth/verify
Body: {"partner_token": "partner_demo_token_001"}
Response: {"session_id": "...", "user_id": "...", "recent_history": [...]}
```

### WebSocket 채팅

```
WS /api/v1/chat/{session_id}
```

- **연결**: `session_id`는 `/auth/verify` 응답의 값 사용 (형식: `{user_id}_{timestamp}`)
- **전송**: `{"message": "감초 효능이 뭐야?", "user_id": "..."}` (user_id는 session_id에서 추출 가능 시 생략)
- **수신**: `{"type": "status"|"token"|"end", "content": "..."}`

## 통합 테스트 가이드

### 1. 인증 테스트

```bash
curl -X POST http://localhost:8000/api/v1/auth/verify \
  -H "Content-Type: application/json" \
  -d '{"partner_token": "partner_demo_token_001"}'
```

### 2. WebSocket 테스트 (websocat 또는 브라우저)

```bash
# websocat 설치 후
websocat ws://localhost:8000/api/v1/chat/{session_id}
# 위에서 받은 session_id 사용 (예: abc123_1710000000000)

# 메시지 전송 (JSON)
{"message": "감초 효능 알려줘", "user_id": "위 응답의 user_id"}
```

### 3. 라우팅별 테스트 메시지

| 라우트 | 예시 메시지 |
|--------|-------------|
| GRAPH | "감초 효능이 뭐야?", "대추와 궁합 좋은 한약재" |
| DB_SQL | "재고 수량 알려줘", "단가 얼마야" |
| GENERAL | "안녕", "날씨 어때?" |

## 디렉토리 구조

```
app/
├── api/          # 라우터, WebSocket, 인증
├── core/         # 설정, DB/Redis 연결
├── models/       # SQLAlchemy 스키마
├── services/     # LLM 라우터, 챗봇 로직, Redis 워커
└── utils/        # 프롬프트, 헬퍼
```

## 환경 변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| DATABASE_URL | PostgreSQL 연결 문자열 | postgresql+asyncpg://... |
| REDIS_URL | Redis 연결 문자열 | redis://localhost:6379/0 |
| OPENAI_API_KEY | OpenAI API 키 (없으면 Mock) | - |
| USE_MOCK_LLM | Mock 모드 강제 | true |
