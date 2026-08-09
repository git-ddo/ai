# AI Server

GitHub Repository의 구조화된 근거와 사용자 입력을 바탕으로 취업용 포트폴리오 코칭 리포트를 생성하는 AI 서버이다.

전체 서비스 기획은 루트 [`README.md`](../README.md), 상세 AI 개발 명세는 [`guide.md`](../docs/guide.md), AI 에이전트 작업 규칙은 [`AGENTS.md`](../AGENTS.md)를 참고한다.

> Phase 1의 서버 기반 구성이 완료되었으며 현재는 Phase 2의 API 계약을 구현하는 단계이다.

## 책임 범위

AI 서버는 다음 작업을 담당한다.

- 백엔드 요청 데이터 검증 및 정규화
- 희망 직무와 분석 목적에 맞는 평가 기준 선택
- Repository별 포트폴리오 분석
- 전체 포트폴리오 진단과 대표 프로젝트 추천
- GitHub 정리 로드맵 생성
- 면접 질문과 답변 가이드 생성
- 이력서·포트폴리오·면접용 문장 생성
- LLM의 구조화된 출력과 근거 검증

다음 작업은 AI 서버의 책임이 아니다.

- GitHub OAuth 및 사용자 인증
- GitHub API 직접 호출
- 사용자, 분석 상태 및 리포트의 영속화
- Repository 전체 원본 저장
- commit 수를 이용한 기여도 또는 실력 계산
- Private Repository 접근 권한 관리

## 데이터 흐름

```text
Spring Boot Backend
  └─ GitHub 근거, 백엔드 계산 지표, 사용자 입력 전달
          ↓ JSON
FastAPI AI Server
  ├─ Pydantic 요청 검증
  ├─ 입력 정규화
  ├─ 직무별 Criteria 및 분석 목적별 Prompt 선택
  ├─ LLM Structured Output 생성
  └─ 근거 및 응답 Schema 검증
          ↓ JSON
Spring Boot Backend
  └─ 최종 리포트 저장 및 Frontend 제공
```

분석 데이터는 항상 다음 세 범주를 구분한다.

1. `GITHUB`: GitHub에서 확인된 객관적 근거
2. `USER_PROVIDED`: 사용자가 직접 입력한 역할과 경험
3. `BACKEND_DERIVED`: 백엔드 규칙으로 계산된 결과

AI가 만든 해석과 추천은 입력에서 확인된 사실로 표현하지 않는다.

## 기술 스택

| 영역 | 기술 |
|---|---|
| Language | Python 3.12+ |
| API | FastAPI, Uvicorn |
| Schema | Pydantic v2 |
| Settings | pydantic-settings |
| LLM | Google Gen AI SDK (`google-genai`), Gemini Structured Output |
| Retry | tenacity |
| Criteria | PyYAML |
| Test | pytest, pytest-asyncio |
| Quality | Ruff, mypy 또는 pyright |
| Infrastructure | Docker, GitHub Actions |

MVP에서는 LangChain, RAG, Vector Database, Fine-tuning 및 자체 ML 모델을 사용하지 않는다.

## 디렉토리 구조

```text
ai/
├── app/
│   ├── main.py
│   ├── api/            # FastAPI endpoint
│   ├── core/           # 설정, 예외, 로깅
│   ├── schemas/        # Pydantic 요청·응답 모델
│   ├── criteria/       # 직무별 YAML 평가 기준
│   ├── prompts/        # 시스템 및 분석 Prompt
│   ├── llm/            # LLM Provider 인터페이스와 구현
│   ├── services/       # 분석 유스케이스
│   └── validators/     # 근거 및 최종 리포트 검증
├── tests/
│   └── fixtures/
├── .env.example
├── Dockerfile
├── pyproject.toml
└── README.md
```

Phase 2 이후에 구현할 모듈은 현재 빈 구조로 유지하며 각 단계에서 테스트와 함께 구현한다.

## API

### Health Check

```http
GET /health
```

```json
{
  "status": "UP"
}
```

### 포트폴리오 리포트 생성

```http
POST /ai/v1/portfolio-reports
Content-Type: application/json
```

초기 MVP에서는 동기 HTTP API로 구현한다. 장시간 분석의 Job 및 상태 관리는 Spring Boot가 담당한다.

요청에는 다음 정보가 포함된다.

- `schemaVersion`
- `analysisId`
- `targetJob`
- `analysisPurpose`
- 최대 5개의 `repositories`
- Repository별 GitHub 근거, 백엔드 계산 지표 및 사용자 역할

응답은 자유 형식 Markdown이 아닌 Pydantic 모델로 검증된 JSON이다. 상세 요청·응답 예시는 [`guide.md`](../docs/guide.md)를 참고한다.

## 개발 순서

1. FastAPI 프로젝트와 `/health` 구성
2. 요청·응답 Pydantic 모델 및 API 계약 확정
3. LLM 없이 고정 응답을 반환하는 Mock API 구현
4. 직무별 Criteria와 분석 목적별 Prompt Routing 구현
5. LLM Provider 및 Gemini Structured Output 연동
6. Repository별 분석과 전체 포트폴리오 종합 구현
7. Evidence Validator와 실패 정책 구현
8. 백엔드 통합 및 품질 평가

각 단계는 formatter, lint, type check 및 test가 통과한 뒤 다음 단계로 진행한다.

## 환경변수

예정된 환경변수는 다음과 같다.

```env
APP_ENV=local
APP_HOST=0.0.0.0
APP_PORT=8000

LLM_PROVIDER=gemini
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.6-flash
LLM_TIMEOUT_SECONDS=60
LLM_MAX_RETRIES=2

MAX_REPOSITORIES=5
MAX_REQUEST_BYTES=
LOG_LEVEL=INFO
```

실제 API key와 비밀값은 커밋하지 않는다.

## 실행 및 검증

현재 다음 항목을 로컬과 CI에서 검증한다.

```bash
pytest
ruff check .
ruff format --check .
mypy app
docker build -t gitddo-ai .
```

## 핵심 품질 기준

- 입력에 없는 기술이나 파일을 근거로 사용하지 않는다.
- GitHub 근거와 사용자 입력을 하나의 사실처럼 혼합하지 않는다.
- commit 수를 개인 기여도 또는 역량으로 해석하지 않는다.
- 포트폴리오 준비도 점수를 사용자의 실력이나 취업 가능성으로 표현하지 않는다.
- LLM 응답은 JSON Schema와 Evidence 검증을 통과한 후에만 반환한다.
- timeout, rate limit, 잘못된 JSON 및 근거 없는 핵심 주장을 명시적으로 처리한다.
