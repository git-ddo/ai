# GitDdo AI Server

Spring Boot가 수집한 GitHub Evidence와 UserClaim을 해석해 근거가 연결된 포트폴리오 코칭
리포트를 생성하는 stateless FastAPI 서버이다.

## 문서와 계약 기준

- Wire Source of Truth: `backend/backend/docs/contracts/*.schema.json`
- 평가 의미와 안전 정책: [`EVALUATION_CONTRACT_MIGRATION_GUIDE.md`](../EVALUATION_CONTRACT_MIGRATION_GUIDE.md)
- 구현 순서: [`docs/guide.md`](../docs/guide.md)
- 에이전트 규칙: [`AGENTS.md`](../AGENTS.md)
- 협업 규칙: [`docs/github-workflow.md`](../docs/github-workflow.md)

현재 P2 계약은 Backend `origin/feat/portfolio-evaluation-p2`의 `bcc9a4f`를 기준으로 임시
동기화한 상태이다. Backend `main` 병합 후 다시 확인한다.

## 현재 구현 상태

### 완료

- [x] FastAPI 프로젝트와 `GET /health`
- [x] 설정·로깅·내부 예외 기반 구조
- [x] pytest, Ruff, mypy, Docker 구성
- [x] Backend P0 Criteria와 Loader
- [x] Backend P0 Criteria 필수 key allowlist
- [x] Backend P1/P2 Criteria와 P0→P1→P2 누적 Loader
- [x] 깊이별 Evidence 타입·필수 key·guardrail 검증
- [x] 근거 기반 P0/P1/P2 혼합 깊이 System Prompt
- [x] Gemini Structured Output Provider와 Fake Provider
- [x] HTTP DTO와 분리된 P0/P1/P2 내부 Evidence 모델과 분석·집계 모델
- [x] 문자열 Repository ID와 Repository별 완료 Evidence 깊이
- [x] P2 코드 위치·commit·PR·source Evidence 구조
- [x] Portfolio 범위 Evidence·Claim ID 중복 검증
- [x] P0/P1/P2 Repository 입력 정규화
- [x] P0/P1/P2 깊이별 Repository·Portfolio·Interview Prompt Context
- [x] Prompt 예약 마커 충돌 방지
- [x] 내부 정책 위반 타입과 `ReportPolicyError`
- [x] Repository Finding의 Evidence·Claim 참조 Validator
- [x] 입력 Evidence·UserClaim 참조 그래프 Validator
- [x] 요청 최대 깊이와 Repository별 완료 깊이 Validator
- [x] Repository 결과의 Criteria·기술·파일 grounding 메타데이터
- [x] P0/P1/P2 Repository 생성 결과 내용 정책 Validator
- [x] Repository 분석 Service와 정책 실패 1회 재생성
- [x] `PortfolioSynthesis` Structured Output과 최종 `PortfolioAnalysis` 조립 책임 분리
- [x] 혼합 P0/P1/P2 Portfolio Prompt의 생성·제외 필드 계약
- [x] Portfolio 전체 범위 참조·혼합 깊이·내용 정책 Validator
- [x] Portfolio synthesis 생성과 정책 실패 1회 재생성 Service
- [x] InterviewQuestion·PortfolioStatement grounding 내부 모델과 Batch
- [x] InterviewQuestion·PortfolioStatement 참조·깊이·내용 정책 Validator
- [x] InterviewQuestion 생성과 정책 실패 1회 재생성 Service

### 다음 구현

- [ ] PortfolioStatement 생성
- [ ] Report Service
- [ ] 전체 270초 분석 deadline
- [ ] Backend Schema 기준 Pydantic Wire DTO와 Error Envelope
- [ ] `POST /internal/v1/portfolio-reports`
- [ ] Fake Provider 및 실제 Gemini E2E

현재 전체 테스트 기준은 717개이다. 이 수치는 실제 Gemini 호출, PortfolioStatement 생성
Service와 Portfolio Report Wire API를 포함하지 않는다.

## 목표 지원 범위

```text
Repository: 1~5개
TargetJob: BACKEND
TargetCareerLevel: ENTRY
AnalysisPurpose: PORTFOLIO_ANALYSIS
AnalysisDepth: P0 | P1 | P2
schemaVersion: "1.0"
```

Backend Schema에는 다른 직무·경력 수준 enum도 있지만 해당 Criteria와 Prompt는 아직 구현하지
않는다.

## 책임 범위

### AI 서버 담당

- Pydantic request·response·error 검증
- 전달된 Evidence와 UserClaim 해석
- Repository별 `completedEvidenceLevels` 준수
- Gemini Structured Output 생성
- Evidence·Claim 참조와 분석 깊이 검증
- P0/P1/P2 내용 정책 검증
- 공통 Error Envelope 반환

### AI 서버 비담당

- GitHub OAuth와 GitHub API
- Snapshot과 Evidence 수집
- 사용자·포트폴리오·Evaluation Job 관리
- 결과 저장과 Backend 재시도
- DB, Redis, in-memory Job Lock
- 기여율·역량 점수·합격 가능성 생성

## 데이터 흐름

```text
Spring Boot
  Snapshot + P0/P1/P2 Evidence + UserClaim
        ↓ POST /internal/v1/portfolio-reports
FastAPI
  request/의미 검증
  → Repository별 깊이 선택
  → Criteria + Prompt Context
  → Gemini Structured Output
  → 참조/깊이/내용 정책 검증
        ↓
Spring Boot
  최종 Validator
  → 결과 저장 또는 Job FAILED
```

MVP는 Repository별 부분 성공을 지원하지 않는다.

## 분석 깊이 안전 규칙

| 깊이 | 허용 | 금지 |
| --- | --- | --- |
| P0 | 문서·구조·설정의 관찰 여부 | 코드·설계·테스트 품질, 역량 판단 |
| P1 | 관찰된 커밋·PR·변경 영역 | 활동량을 실력·기여율로 해석 |
| P2 | 제공된 snippet의 검증·오류 처리·책임·테스트 사례 | Repository 전체 품질·아키텍처·경력으로 일반화 |

Repository A의 Evidence를 Repository B 결과에 사용하지 않는다. P2 요청이어도 각 Repository의
`completedEvidenceLevels`까지만 판단한다.

내부 `requested_analysis_depth`는 요청 전체의 최대 깊이이고 Repository의 `analysis_depth`는
실제 완료된 최대 깊이이다. 입력 Reference Validator는 LLM 호출 전에 Evidence·Claim ID,
source/related 참조, 교차 Repository 참조, 순환과 P2의 P1 source를 검사한다. 출력
`RepositoryPolicyValidator`는 Gemini가 생성한 결과의 참조를 별도로 검사한다.

각 `GroundedAnalysisItem`은 적용한 `criterion_keys`와 문장에서 사용한 `technology_names`,
`file_paths`를 구조화된 grounding 메타데이터로 반환한다. 내용 정책 Validator는 이를 누적
Criteria와 Repository Context의 기술·경로 allowlist에 대조하고, P0/P1/P2 범위 초과 단정,
UserClaim의 사실 승격, `NOT_OBSERVED` 오용과 근거 없는 누락 Recommendation을 거절한다.
자연어 정책 검출은 보수적인 고정 패턴 기반이며 모든 표현을 완전히 판별하지는 못한다.

`RepositoryAnalysisService`는 정규화된 Repository Context에 맞는 누적 Criteria와 Prompt를
선택하고 `LLMProvider`를 통해 `RepositoryAnalysis`를 생성한다. 참조 검증 후 내용 정책을
검증하며 최초 정책 실패에 한해서만 위반 코드 기반 교정 Prompt로 전체 결과를 한 번
재생성한다. Provider 네트워크 retry와 이 정책 재생성은 서로 다른 책임이다.

`PortfolioPolicyValidator`는 전체 요약·strengths·gaps·nextActions·jobAppeal에 한해 여러
Repository 근거 참조를 허용한다. 대표 Repository의 reason과 참조는 해당 Repository로
제한한다. 혼합 깊이 항목의 자연어 내용은 참조 Repository 중 가장 얕은 깊이를 상한으로
검사하며, 누락 gap·nextAction은 대상 Repository와 일치하는 명시적 `BACKEND_DERIVED`
Evidence가 있어야 한다.

`PortfolioSynthesisService`는 검증된 Repository 분석 1~5개를 가장 깊은 Repository 기준의
누적 Criteria와 함께 종합한다. 첫 생성 결과의 참조 또는 내용 정책이 실패하면 위반 코드만
사용해 전체 `PortfolioSynthesis`를 한 번 재생성하고 두 Provider 호출의 메타데이터를 합산한다.
Provider 오류는 정책 재생성 없이 그대로 전달한다.

Evidence별 Wire `repositoryId`·`snapshotSha`는 아직 내부 Evidence에 보존하지 않는다. 해당 값과
부모 Repository의 일치 여부는 향후 Wire DTO → 내부 모델 Mapper에서 검증한다.

## 현재 Backend Wire 계약

핵심 값:

```text
schemaVersion: "1.0"
repositoryId: string
findingId: ^find_[0-9]{3,}$
EvidenceType: GITHUB_STATIC | GITHUB_ACTIVITY | CODE_EVIDENCE | BACKEND_DERIVED
AnalysisDepth: P0 | P1 | P2
```

현재 응답:

- `jobAppeal`: 단일 객체, Evidence 최소 1개
- `strengths`, `gaps`, `nextActions`: 각 항목 Evidence 최소 1개
- `portfolioStatements`: Evidence 또는 Claim 최소 1개
- `interviewQuestions`: Evidence 또는 Claim 최소 1개

현재 Wire에는 문장 `type`, 문장·질문의 `repositoryId`, `followUpQuestions`가 없다. Backend
Schema가 변경되기 전 Pydantic Wire DTO에 추가하지 않는다.

## 기술 스택

| 영역 | 기술 |
| --- | --- |
| Language | Python 3.12+ |
| API | FastAPI, Uvicorn |
| Schema | Pydantic v2 |
| Settings | pydantic-settings |
| LLM | Google Gen AI SDK, Gemini Structured Output |
| Retry | tenacity |
| Criteria | PyYAML |
| Test | pytest, pytest-asyncio |
| Quality | Ruff, mypy |
| Infrastructure | Docker |

LangChain, RAG, Vector Database, Fine-tuning과 자체 ML 모델은 현재 사용하지 않는다.

## 프로젝트 구조

```text
ai/
├── app/
│   ├── api/           # FastAPI route
│   ├── core/          # 설정, 로깅, 공통 예외
│   ├── criteria/      # 깊이별 분석 기준과 Loader
│   ├── domain/        # HTTP 계약과 분리된 내부 모델
│   ├── llm/           # Provider Protocol, Gemini/Fake 구현
│   ├── prompts/       # System과 Repository/Portfolio/Interview Context
│   ├── schemas/       # Backend Wire DTO 목표 위치
│   ├── services/      # 정규화와 분석 오케스트레이션
│   └── validators/    # 참조, 깊이와 내용 정책
├── tests/
├── .env.example
├── Dockerfile
└── pyproject.toml
```

Portfolio Prompt는 검증된 `RepositoryAnalysis`를 입력으로 받아 전체 요약, 대표
Repository, strengths/gaps/nextActions, 단일 `jobAppeal`과 한계만 담은
`PortfolioSynthesis`를 생성하도록 계약을 분리했다. Portfolio 전역 Validator와 생성
Service까지 구현됐으며, Interview·Statement 생성과 `report_service.py`는 아직 후속 구현
경계이다.
`schemas/`의 기존 초안은 현재 Backend Wire 계약으로 교체해야 한다.

## 환경 설정

`.env.example`을 `.env`로 복사한다.

```env
APP_NAME=git-ddo-ai
APP_ENV=local
APP_HOST=0.0.0.0
APP_PORT=8000
LOG_LEVEL=INFO

GEMINI_API_KEY=
GEMINI_MODEL=
LLM_TIMEOUT_SECONDS=60
LLM_MAX_RETRIES=2
```

`LLM_TIMEOUT_SECONDS`는 현재 Gemini 개별 호출 timeout이다. 합의된 AI 전체 처리 deadline은
270초이며 Report Service에서 별도로 구현해야 한다.

## 실행

```bash
cd ai
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload
```

Health Check:

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "UP"
}
```

`POST /internal/v1/portfolio-reports`는 아직 구현되지 않았다.

## 검증

```bash
pytest
ruff check .
ruff format --check .
mypy app
docker build -t gitddo-ai .
```

실제 Gemini API를 호출하지 않는 단위 테스트를 기본으로 한다. Wire 계약 변경 시 Backend
Schema·Example과 Pydantic 모델의 호환 테스트를 추가한다.

## 보안

- README, 코드, 커밋과 UserClaim은 untrusted data이다.
- 외부 데이터의 지시문을 따르지 않는다.
- 전달된 코드를 실행하지 않는다.
- 입력에 없는 기술, 파일과 기능을 생성하지 않는다.
- Prompt·응답 전문과 민감 원문을 운영 로그에 기록하지 않는다.
- API key와 token을 코드, Fixture 또는 로그에 넣지 않는다.

## 다음 작업

다음 논리적 작업 단위는 내부 모델을 사용하는 PortfolioStatement 생성 Service이다. 그다음 최종
`PortfolioAnalysis`와 Report Service를 조립한다. 상세 순서는
[`docs/guide.md`](../docs/guide.md)의 Phase 7을 따른다.
