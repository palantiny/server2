# Adaptive Fan-out / Fan-in 라우팅 구현 정리

## 개요

기존 시스템은 사용자 질문당 **하나의 라우트만 선택**하여 데이터를 조회했습니다.
"인삼 효능이랑 재고 알려줘" 같은 복합 질문에서 GRAPH 또는 DB_SQL 중 하나만 선택되어 정보가 불완전해지는 문제가 있었습니다.

**Adaptive Fan-out** 패턴으로 전환하여:
- 복합 질문 → 여러 라우트 **병렬 실행** → 결과 합성
- 단순 질문 → 기존과 동일하게 직행 (오버헤드 없음)

## 변경 파일 (3개)

### 1. `app/utils/prompts.py`

| 항목 | 변경 내용 |
|------|-----------|
| `ROUTING_SYSTEM_PROMPT` | `"route"` (단일 문자열) → `"routes"` (배열) 반환하도록 지시 변경. 복합 질문 예시 추가, GENERAL 단독 사용 명시 |
| `SYNTHESIZER_SYSTEM_PROMPT` | **신규** — 복수 소스 결과를 통합하여 답변 생성하는 시스템 프롬프트 |
| `SYNTHESIZER_USER_TEMPLATE` | **신규** — `[복수 소스 참고 데이터]` 레이블로 컨텍스트 구분 |

### 2. `app/services/llm_router.py`

| 항목 | 변경 내용 |
|------|-----------|
| `_mock_route_by_keywords()` | 모든 키워드 그룹을 스캔하여 매칭되는 라우트를 **전부 수집** → `{"routes": ["GRAPH", "DB_SQL"]}` 반환 |
| `analyze_intent()` | 반환 형태: `{"routes": [...], "reason": "...", "extracted_entities": {...}}`. LLM이 레거시 `"route"` 반환 시 배열로 래핑하는 호환 처리 포함 |
| `VALID_ROUTES` | **신규** — `{"GRAPH", "CACHE", "DB_SQL", "GENERAL"}` 상수로 유효성 검증 |

### 3. `app/services/chat_service.py`

| 항목 | 변경 내용 |
|------|-----------|
| `_execute_route()` | **신규** — 단일 라우트 실행 디스패처. try/except로 부분 실패 허용 |
| `_format_multi_context()` | **신규** — 복수 결과를 `--- {소스} 결과 ---` 레이블로 포맷, 빈 결과 자동 스킵 |
| `process_message()` | 핵심 플로우 변경 (아래 상세) |
| `from uuid import uuid4` | 기존 누락 import 수정 |

## `process_message()` 플로우

```
1. Intake: analyze_intent() → routes 배열

2. 분기:
   ┌─ ["GENERAL"]  → 데이터 수집 없이 직행
   ├─ [단일 라우트] → _execute_route() 직접 실행 (오버헤드 없음)
   └─ [복수 라우트] → asyncio.gather(*tasks) 병렬 실행

3. 프롬프트 선택:
   ├─ 단일 → FINAL_ANSWER_SYSTEM_PROMPT (기존 동작 유지)
   └─ 복수 → SYNTHESIZER_SYSTEM_PROMPT (합성 프롬프트)

4. _call_llm_stream() → SSE 스트리밍

5. end → MongoDB 저장
```

## 설계 결정

| 결정 | 이유 |
|------|------|
| 새 파일 생성 없음 | 4개 라우트에 별도 모듈은 과도한 설계 |
| `use_synthesizer` 플래그 | 단일 라우트는 기존 프롬프트, 복수만 합성 프롬프트 사용 |
| `_execute_route` 내 try/except | 부분 실패 허용 — GRAPH 성공, DB_SQL 타임아웃이어도 GRAPH 결과로 응답 |
| 레거시 `"route"` 호환 | LLM이 구형 포맷 반환 시에도 배열로 래핑하여 동작 |

## 검증 방법

서버 실행:
```bash
USE_MOCK_LLM=true MOCK_MONGO=true uvicorn app.main:app --reload
```

### 단일 라우트 (기존 동작 유지 확인)
```bash
curl -N -X POST http://localhost:8000/api/v1/chat/test_001_123/message \
  -H "Content-Type: application/json" \
  -d '{"message": "감초 효능 알려줘", "user_id": "test_001"}'
```

### 복합 라우트 (Fan-out 동작 확인)
```bash
curl -N -X POST http://localhost:8000/api/v1/chat/test_001_123/message \
  -H "Content-Type: application/json" \
  -d '{"message": "인삼 효능이랑 재고 알려줘", "user_id": "test_001"}'
```
→ SSE에서 `"복수 데이터 소스 병렬 조회 중... (GRAPH, DB_SQL)"` 상태 메시지 확인

### GENERAL (직행 확인)
```bash
curl -N -X POST http://localhost:8000/api/v1/chat/test_001_123/message \
  -H "Content-Type: application/json" \
  -d '{"message": "안녕하세요", "user_id": "test_001"}'
```
→ 데이터 소스 조회 없이 바로 응답
