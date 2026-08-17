# GitDdo AI Server

Spring Boot가 수집·구조화한 GitHub Evidence와 UserClaim을 해석하여 근거가 연결된 포트폴리오 코칭 리포트를 생성하는 stateless FastAPI 서버이다.

## 문서 기준

- 최종 계약 기준: [`EVALUATION_CONTRACT_MIGRATION_GUIDE.md`](../EVALUATION_CONTRACT_MIGRATION_GUIDE.md)
- 단계별 개발 절차: [`docs/guide.md`](../docs/guide.md)
- 에이전트 작업 규칙: [`AGENTS.md`](../AGENTS.md)
- 협업 규칙: [`docs/github-workflow.md`](../docs/github-workflow.md)

공용 계약 구현 후 `docs/contracts/`의 JSON Schema와 Fixture를 백엔드와 함께 사용한다.

## 현재 구현 상태

- [x] FastAPI 프로젝트와 `/health`
- [x] 설정, 로깅, 예외 기반 구조
- [x] pytest, Ruff, mypy, Docker 구성
- [x] Backend P0 Criteria와 Loader
- [x] 근거 기반 System Prompt
- [x] 독립형 Gemini Provider
- [ ] 내부 P0 분석 파이프라인
- [ ] 최종 `contractVersion = "1.0"` Pydantic 계약
- [ ] 공용 JSON Schema와 Fixture
- [ ] 요청·응답 의미 Validator
- [ ] `POST /internal/v1/portfolio-reports` Mock API
- [ ] Spring Boot Mock 연동과 실제 E2E

기존 Pydantic 계약은 초기 초안이며 최종 계약으로 교체해야 한다. 구현 완료 여부는 코드와 테스트를 기준으로 갱신한다.

## MVP 지원 범위

```text
Repository: 1~5개
TargetJob: BACKEND
TargetCareerLevel: ENTRY
AnalysisPurpose: PORTFOLIO_ANALYSIS
AnalysisDepth: P0
ContractVersion: 1.0
```

다른 직무·경력 수준과 P1/P2는 계약 확장 타입으로만 정의한다. 현재 요청되면 `UNSUPPORTED_COMBINATION`을 반환한다.

## 책임 범위

### 담당

- Pydantic 요청·응답·오류 검증
- MVP 지원 조합 검증
- 전달된 Evidence와 UserClaim 해석
- Gemini Structured Output 생성
- Evidence/Claim 참조 무결성 검증
- 저장소별 분석 깊이 검증
- `jobAppeal`, Recommendation, `portfolioStatements` 근거 규칙 검증
- 공통 Error Envelope 반환

### 담당하지 않음

- GitHub OAuth와 GitHub API 호출
- Snapshot과 Evidence 수집
- 사용자·포트폴리오·Evaluation Job 관리
- 결과 저장과 멱등성 처리
- 동일 `analysisId` 중복 실행 차단
- DB, Redis, in-memory Job Lock
- 기여율·역량 점수·합격 가능성 생성

## 데이터 흐름

```text
Spring Boot
  Snapshot + Evidence + UserClaim 구성
  Request JSON Schema 검증
        ↓
POST /internal/v1/portfolio-reports
        ↓
FastAPI
  Pydantic 검증
  → 지원 조합·참조·깊이 검증
  → Gemini 호출
  → Pydantic 응답 검증
  → Evidence/Claim/깊이 검증
        ↓
Response JSON 또는 Error Envelope
        ↓
Spring Boot
  최종 Schema와 allowlist 검증 후 저장
```

Spring Boot가 timeout 후 같은 요청을 재호출하면 LLM이 중복 실행될 수 있으며 MVP에서는 허용한다. AI 서버는 요청별로 독립 실행한다.

## 계약 개념

```text
Evidence
GitHub 또는 백엔드가 확인·도출한 사실

UserClaim
사용자가 입력한 역할과 경험

ReportItem
AI가 생성한 관찰·해석·추천·면접 질문
```

핵심 규칙:

- `contractVersion`은 `"1.0"`만 허용한다.
- `analysisId`는 UUID v4이다.
- Evidence 타입은 `GITHUB_STATIC`, `GITHUB_ACTIVITY`, `CODE_EVIDENCE`, `BACKEND_DERIVED`이다.
- P0에서는 `GITHUB_STATIC`, `BACKEND_DERIVED`만 허용한다.
- 모든 Recommendation은 `evidenceRefs`를 최소 1개 포함한다.
- `jobAppeal`은 공개 Evidence를 최소 1개 포함하며 Claim만으로 만들지 않는다.
- `portfolioStatements`는 `evidenceRefs` 또는 `claimRefs` 중 최소 하나를 포함한다.
- `NOT_OBSERVED`는 부재·거짓·미기여를 뜻하지 않는다.
- 잘못된 항목을 제거한 부분 성공을 반환하지 않는다.

## 기술 스택

| 영역 | 기술 |
|---|---|
| Language | Python 3.12+ |
| API | FastAPI, Uvicorn |
| Schema | Pydantic v2 |
| Settings | pydantic-settings |
| LLM | Google Gen AI SDK(`google-genai`), Gemini Structured Output |
| Retry | tenacity |
| Criteria | PyYAML |
| Test | pytest, pytest-asyncio |
| Quality | Ruff, mypy |
| Infrastructure | Docker, GitHub Actions |

MVP에서는 LangChain, RAG, Vector Database, Fine-tuning 및 자체 ML 모델을 사용하지 않는다.

## 목표 디렉터리 구조

```text
ai/
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── health.py
│   │   └── reports.py
│   ├── core/
│   │   ├── config.py
│   │   ├── exceptions.py
│   │   └── logging.py
│   ├── schemas/
│   │   ├── common.py
│   │   ├── enums.py
│   │   ├── evidence.py
│   │   ├── claims.py
│   │   ├── repository.py
│   │   ├── request.py
│   │   ├── response.py
│   │   └── error.py
│   ├── criteria/
│   ├── prompts/
│   ├── llm/
│   ├── services/
│   └── validators/
│       ├── evidence_validator.py
│       ├── depth_validator.py
│       └── report_validator.py
├── scripts/
│   └── export_contracts.py
├── tests/
│   └── fixtures/
├── .env.example
├── Dockerfile
└── pyproject.toml
```

공용 계약 Fixture는 루트 `docs/contracts/fixtures/`에 둔다. `ai/tests/fixtures/`에는 AI 서버 전용 실패·Prompt Injection Fixture만 둔다.

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
POST /internal/v1/portfolio-reports
Content-Type: application/json
```

요청·응답 예시는 공용 계약 Fixture로 관리한다. 최종 wire format 확정 전 README에 별도 대형 JSON을 복제하지 않는다.

## 개발 순서

백엔드와 실제 HTTP 연동은 최대한 뒤로 미룬다. AI와 백엔드는 Fake·Stub을 사용하여 각자의 핵심 기능을 독립적으로 완성한다.

1. Backend P0 Criteria와 Loader 구현
2. 근거 기반 System Prompt와 Prompt Injection 방어 구현
3. `LLMProvider`와 Gemini Provider 기반 구현
4. 내부 모델을 사용한 P0 분석 파이프라인 구현
5. 백엔드 P0 Collector·Evidence 생성과 양쪽 독립 테스트 완료
6. 실제 사용 데이터를 비교하여 최종 Pydantic·Java DTO 확정
7. JSON Schema와 공용 Fixture 생성
8. 요청·응답 참조 및 분석 깊이 Validator 구현
9. Mock 내부 API로 계약 연동
10. 실제 Gemini 분석과 Spring Boot E2E 연동

최종 wire DTO는 내부 분석 모델과 분리한다. Fixture는 DTO 의미를 확정한 뒤 생성하며 선확정을 요구하지 않는다.

단계별 체크리스트와 커밋 단위는 [`docs/guide.md`](../docs/guide.md)를 따른다.

## 환경변수

```env
APP_ENV=local
APP_HOST=0.0.0.0
APP_PORT=8000

LLM_PROVIDER=gemini
GEMINI_API_KEY=
GEMINI_MODEL=
LLM_TIMEOUT_SECONDS=60
LLM_MAX_RETRIES=2

MAX_REPOSITORIES=5
MAX_REQUEST_BYTES=2097152
LOG_LEVEL=INFO
```

실제 API key, token, 개인정보와 Repository 원문은 커밋하거나 운영 로그에 남기지 않는다.

## 실행과 검증

```bash
pytest
ruff check .
ruff format --check .
mypy app
docker build -t gitddo-ai .
```

계약 변경 시 Pydantic 직렬화, 공용 Fixture, Draft 2020-12 JSON Schema 및 참조 무결성 테스트를 함께 실행한다.

## 보안 기준

- README·코드·커밋·사용자 입력을 untrusted data로 처리한다.
- 외부 입력에 포함된 지시문을 따르지 않는다.
- 전달된 코드를 실행하지 않는다.
- 저장소 전체 코드와 GitHub raw response를 받지 않는다.
- LLM 요청·응답 전문을 운영 로그에 남기지 않는다.
- P0 요청은 최대 2 MiB로 제한한다.
