# Palantiny (팔란티니) - 한약재 유통 B2B2C 챗봇 서버

FastAPI 기반의 한약재 유통 자동화 챗봇 서버입니다. SSE(Server-Sent Events)로 실시간 스트리밍 응답과 thinking 과정을 제공합니다.

## 기술 스택

- Python, FastAPI, SSE (StreamingResponse)
- **PostgreSQL** - 한약재 마스터/재고 데이터 (herb_master, inventory)
- **MongoDB** - 채팅 히스토리 저장 (MOCK_MONGO=true 시 메모리 저장소 사용)
- **Redis** - 캐시, Queue, Pub/Sub
- OpenAI (선택, Mock 모드 지원)

## 아키텍처

- **질문 라우팅**: LLM이 질문 의도를 파악해 → GRAPH(지식그래프) / CACHE(Redis 캐시) / DB_SQL(Text-to-SQL) / GENERAL 중 하나로 분기
- **채팅 히스토리**: MongoDB에 저장, 로그인 인증 후 히스토리 로드
- **128k Context**: 대화 맥락이 128k 토큰 초과 시 LLM으로 요약
  - 요약 후 최근 대화와 결합해 context 유지

---

## 차근차근 실행 가이드 (인증 → LLM 출력까지)

### Step 1: Docker Compose로 서비스 기동

터미널에서 프로젝트 폴더로 이동한 뒤:

```bash
docker-compose up -d
```

- PostgreSQL(5432), Redis(6379), App(8000) 컨테이너가 실행됩니다.
- `MOCK_MONGO=true`(기본값)이면 MongoDB 없이 메모리 저장소로 채팅 히스토리 동작.
- 실제 MongoDB 사용 시: `MOCK_MONGO=false`, `MONGODB_URI` 설정 후 MongoDB 컨테이너 추가.
- `docker-compose ps`로 상태 확인.

---

### Step 2: 시드 데이터 삽입 (User 생성)

인증에 필요한 User와 한약재 데이터를 DB에 넣습니다.

```bash
docker-compose exec app python -m scripts.seed_data
```

예상 출력:
```
Created user: xxx-xxx-xxx, token: partner_demo_token_001
HerbMaster seeded
Inventory seeded
```

---

### Step 3: 인증 (session_id 발급)

**Windows CMD (명령 프롬프트):**
```cmd
curl -X POST http://localhost:8000/api/v1/auth/verify -H "Content-Type: application/json" -d "{\"partner_token\": \"partner_demo_token_001\"}"
```

**Windows PowerShell:**
```powershell
curl.exe -X POST http://localhost:8000/api/v1/auth/verify -H "Content-Type: application/json" -d '{"partner_token": "partner_demo_token_001"}'
```
> PowerShell에서 `curl`은 Invoke-WebRequest 별칭이라, 실제 curl을 쓰려면 `curl.exe`로 실행하세요.

응답 예시:
```json
{
  "session_id": "abc12345-xxxx-xxxx_1710000000000",
  "user_id": "abc12345-xxxx-xxxx",
  "recent_history": []
}
```

- `recent_history`: MongoDB(또는 MOCK 시 메모리)에서 해당 user_id의 최근 대화 로드
- **이 `session_id`를 다음 단계에서 사용합니다.**

---

### Step 4: SSE 채팅 (질문 전송 → 스트리밍 응답)

위에서 받은 `session_id`로 채팅 요청. 아래 `세션ID`를 Step 3 응답의 `session_id` 값으로 바꾸세요.
- Body에 `user_id`를 함께 보내면 히스토리 조회에 사용됩니다. (생략 시 session_id에서 파싱)

**Windows CMD:**
```cmd
curl -X POST "http://localhost:8000/api/v1/chat/세션ID/message" -H "Content-Type: application/json" -d "{\"message\": \"감초 재고 알려줘\"}" --no-buffer
```

**Windows PowerShell:**
```powershell
curl.exe -X POST "http://localhost:8000/api/v1/chat/세션ID/message" -H "Content-Type: application/json" -d '{"message": "감초 재고 알려줘", "user_id": "abc12345-xxxx-xxxx"}' --no-buffer
```

예시 (session_id가 `a1b2c3d4-5678-90ab-cdef-1234567890ab_1710000000000` 인 경우):
```powershell
curl.exe -X POST "http://localhost:8000/api/v1/chat/a1b2c3d4-5678-90ab-cdef-1234567890ab_1710000000000/message" -H "Content-Type: application/json" -d '{"message": "감초 재고 알려줘"}' --no-buffer
```

**`--no-buffer`** 를 꼭 넣어야 스트리밍이 실시간으로 출력됩니다.

예상 출력 (순서대로, 라우팅 결과에 따라 status 다름):
```
data: {"type": "status", "content": "질문 의도 분석 중..."}

data: {"type": "status", "content": "DB 접근을 위한 Text-to-SQL 작업 중..."}
# 또는: "한약재 지식 그래프 탐색 중..." (GRAPH)
# 또는: "CACHE에서 데이터 조회 중..." (CACHE)
# 또는: "이전 대화 맥락 확인 중..." (GENERAL)
# 또는: "대화 맥락 요약 중..." (128k 초과 시)

data: {"type": "token", "content": "안"}
data: {"type": "token", "content": "녕"}
...
data: {"type": "end"}
```

---

### Step 5: (선택) 로컬에서 개발 모드로 실행

Docker 대신 로컬에서 실행하려면:

```cmd
REM PostgreSQL, Redis만 Docker로 실행
docker-compose up -d postgres redis

REM .env 설정
copy .env.example .env

REM MOCK_MONGO=true(기본)이면 MongoDB 없이 동작
REM MongoDB 사용 시: MOCK_MONGO=false, MONGODB_URI 설정

REM 의존성 설치
pip install -r requirements.txt

REM 시드 데이터
python -m scripts.seed_data

REM 서버 실행
uvicorn app.main:app --reload --port 8000
```

이후 Step 3, 4와 동일하게 테스트합니다.

---

## API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| POST | /api/v1/auth/verify | partner_token 검증, session_id 발급 |
| POST | /api/v1/chat/{session_id}/message | SSE 스트리밍 채팅 |

### SSE 응답 형식

- `{"type": "status", "content": "..."}` - 진행 상태
- `{"type": "token", "content": "한"}` - 답변 한 글자
- `{"type": "end"}` - 스트림 종료

---

## 디렉토리 구조

```
app/
├── api/          # 라우터, 인증
├── core/         # 설정, DB/Redis 연결
├── models/       # SQLAlchemy 스키마 (PostgreSQL)
├── repositories/ # ChatHistory (MongoDB/Memory)
├── services/     # LLM 라우터, 챗봇 로직, history_manager, Redis 워커
└── utils/        # 프롬프트, 헬퍼
```

## 환경 변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| DATABASE_URL | PostgreSQL 연결 문자열 | postgresql+asyncpg://... |
| REDIS_URL | Redis 연결 문자열 | redis://localhost:6379/0 |
| MONGODB_URI | MongoDB 연결 문자열 (채팅 히스토리) | mongodb://localhost:27017 |
| MONGODB_DB | MongoDB DB 이름 | palantiny |
| MOCK_MONGO | true 시 메모리 저장소 사용 (MongoDB 불필요) | true |
| OPENAI_API_KEY | OpenAI API 키 (없으면 Mock) | - |
| USE_MOCK_LLM | Mock 모드 강제 | true |
