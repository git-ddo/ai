# AI 서버 개발 가이드

이 문서는 최종 평가 계약을 구현하기 위한 작업 순서와 완료 조건을 정리한다. 계약의 전체 의미와 세부 제한은 루트 [`EVALUATION_CONTRACT_MIGRATION_GUIDE.md`](../EVALUATION_CONTRACT_MIGRATION_GUIDE.md)를 기준으로 한다.

## 1. 목표와 현재 상태

목표는 Spring Boot가 전달한 Evidence와 UserClaim을 바탕으로 근거가 연결된 포트폴리오 코칭 리포트를 생성하는 stateless FastAPI 서버를 구현하는 것이다.

현재 상태:

- [x] FastAPI 기반 환경 구성
- [x] `/health` 구현
- [x] pytest, Ruff, mypy, Docker 기반 구성
- [x] 최종 계약 기준 문서 확정
- [ ] 최종 계약의 미확정 wire format을 백엔드 Fixture로 확정
- [ ] `contractVersion = "1.0"` Pydantic 계약 구현
- [ ] 공용 JSON Schema와 Fixture 생성
- [ ] 의미·참조·분석 깊이 Validator 구현
- [ ] Mock 내부 API 구현
- [ ] Gemini 연동과 실제 리포트 생성

기존 Phase 2 Pydantic 코드는 구 계약 초안이다. reset하지 않고 새 커밋에서 최종 계약으로 교체한다.

## 2. MVP 범위

```text
Repository: 1~5개
TargetJob: BACKEND
TargetCareerLevel: ENTRY
AnalysisPurpose: PORTFOLIO_ANALYSIS
RequestedAnalysisDepth: P0
ContractVersion: 1.0
```

계약 enum에는 확장 값을 정의할 수 있다.

```text
TargetJob: BACKEND, FRONTEND, AI, CLOUD_INFRA
TargetCareerLevel: ENTRY, MID, SENIOR
AnalysisDepth: P0, P1, P2
```

현재 런타임에서 확정 조합 이외의 요청은 `UNSUPPORTED_COMBINATION`으로 거절한다. 네 직무 동시 지원, P1/P2 실행 및 경력 수준 판정은 MVP 완료 기준이 아니다.

## 3. 아키텍처 경계

```text
Frontend
  → 평가 Job 생성·상태 조회
Spring Boot
  → GitHub 수집, Snapshot 고정, Evidence/UserClaim 구성
  → 요청 Schema 검증
  → POST /internal/v1/portfolio-reports
FastAPI AI Server
  → Pydantic/의미 검증
  → Gemini Structured Output
  → 참조·분석 깊이·응답 검증
  → JSON 또는 Error Envelope 반환
Spring Boot
  → 최종 Schema/allowlist 검증
  → 최초 검증 성공 결과 저장
Frontend
  → 저장된 리포트 조회
```

### Spring Boot 책임

- GitHub OAuth와 사용자·포트폴리오 소유권 관리
- `analysisId` UUID v4 생성
- Evaluation Job과 상태 관리
- Snapshot SHA 고정과 Evidence ID 발급
- P0/P1/P2 데이터 수집, Secret 및 불필요 파일 제거
- UserClaim 저장과 AI 요청 구성
- 요청 전 Schema 검증, 응답 최종 검증과 결과 저장
- 클라이언트 `Idempotency-Key`, AI 재호출 및 중복 결과 정책

### AI 서버 책임

- 합의된 요청과 지원 조합 검증
- 전달된 Evidence와 UserClaim만 해석
- 구조화된 코칭 리포트 생성
- Evidence/Claim 참조와 저장소별 분석 깊이 검증
- 공통 Error Envelope 반환

### AI 서버에서 금지

- GitHub API 직접 호출
- 저장소 전체 코드 또는 GitHub raw response 수신
- 사용자·Job·결과·멱등성 정보 저장
- DB, Redis, in-memory Job Lock
- 기여율, 역량 점수, 합격 가능성 생성
- 전달된 코드 실행

## 4. 내부 API

### Health Check

```http
GET /health
```

### 포트폴리오 리포트 생성

```http
POST /internal/v1/portfolio-reports
Content-Type: application/json
```

- 동기 HTTP API이다.
- 정상 응답은 `200 OK`이다.
- Job 상태는 Spring Boot가 관리한다.
- 같은 `analysisId`가 재호출되면 AI 서버는 독립적으로 다시 실행할 수 있다.
- AI 서버는 중복 실행 방지를 위한 저장소나 Lock을 두지 않는다.

## 5. 계약 모델

### Evidence

백엔드가 GitHub에서 확인하거나 규칙으로 도출한 사실이다.

```text
GITHUB_STATIC    P0
GITHUB_ACTIVITY  P1
CODE_EVIDENCE    P2
BACKEND_DERIVED  P0+
```

P0 런타임에서는 `GITHUB_STATIC`, `BACKEND_DERIVED`만 허용한다.

### UserClaim

사용자가 입력한 역할, 참여 수준, 구현 내용과 참여 기간이다. Evidence로 취급하지 않는다.

### GroundedItem과 ReportItem

응답 항목은 문자열 근거 ID를 통해 입력과 연결한다.

```text
evidenceRefs: ["ev_001"]
claimRefs: ["claim_001"]
```

참조 규칙:

| 항목 | 필수 참조 |
|---|---|
| `OBSERVATION` | Evidence |
| `INTERPRETATION` | Evidence 또는 Claim |
| `RECOMMENDATION` | Evidence 최소 1개 |
| 프로젝트 기반 `INTERVIEW_QUESTION` | Evidence 또는 Claim |
| `jobAppeal` | 공개 Evidence 최소 1개, Claim 단독 금지 |
| `portfolioStatements` | Evidence 또는 Claim 최소 1개 |

`portfolioStatements.statementType`은 `RESUME`, `PORTFOLIO`, `INTERVIEW`만 허용한다.

### 누락 기반 판단

AI는 README 섹션, 테스트, 배포 설정 등이 보이지 않았다는 사실을 직접 추론하지 않는다. Spring Boot가 다음과 같은 `BACKEND_DERIVED` Evidence를 전달한 경우에만 관련 Recommendation을 생성한다.

```text
README_SECTION_MISSING
TEST_NOT_OBSERVED
DEPLOYMENT_CONFIG_NOT_OBSERVED
```

`NOT_OBSERVED`는 수집 범위에서 확인하지 못했다는 뜻이며 실제 부재·거짓·미기여를 뜻하지 않는다.

## 6. 버전과 식별자

```text
contractVersion: "1.0"
snapshotSchemaVersion: integer
extractorVersion: string
promptVersion: string

analysisId: UUID v4
repositoryId: GitHub Repository numeric ID
evidenceId: ^ev_[0-9]{3,}$
claimId: ^claim_[0-9]{3,}$
itemId: ^item_[0-9]{3,}$
contentHash: SHA-256 lowercase hex
```

`evidenceId`, `claimId`, `itemId`는 각각 하나의 `analysisId` 전체에서 유일해야 한다. Repository별로 번호를 다시 시작하지 않는다.

## 7. 분석 깊이

| 깊이 | 허용 | 금지 |
|---|---|---|
| P0 | README 준비도, 기술 근거, 테스트·Docker·CI 존재 | 설계 품질, 사용자 역량, 테스트 품질 |
| P1 | 관찰된 활동과 활동 영역 후보 | 기여율, 코드 품질, 활동 부재를 거짓으로 판정 |
| P2 | 제공된 코드 구간의 검증·오류 처리·책임 분리·테스트 | 저장소 전체 품질, 경력 충족 여부 |

분석 깊이는 Repository별 `completedEvidenceLevels`로 관리한다. 응답 항목의 판단 깊이가 참조 Repository의 완료 깊이를 넘으면 전체 리포트를 실패시킨다.

현재는 P0만 실행한다. P1/P2 요청은 `UNSUPPORTED_COMBINATION`이다.

## 8. 요청·응답 책임

### 요청 필수 정보

```text
contractVersion
analysisId
targetJob
targetCareerLevel
analysisPurpose
requestedAnalysisDepth
repositories
```

Repository에는 다음 정보가 포함된다.

```text
repositoryId
repositoryFullName
defaultBranch
snapshotSha
snapshotHashAlgorithm
snapshotSchemaVersion
extractorVersion
completedEvidenceLevels
collectionWarnings
userClaims
evidence
```

### 응답 필수 정보

```text
contractVersion
analysisId
generationMetadata
usedEvidenceLevels
overallDiagnosis
repositoryReports
representativeProjects
jobAppeal
roadmap
interviewQuestions
portfolioStatements
limitations
validationWarnings
```

`generationMetadata`에는 provider, model, promptVersion, generatedAt, durationMs, attemptCount와 tokenUsage를 포함한다.

대형 요청·응답 JSON은 이 문서에 복제하지 않는다. 확정 후 다음 공용 Fixture를 단일 예시로 사용한다.

```text
docs/contracts/fixtures/valid-analysis-request.json
docs/contracts/fixtures/valid-analysis-response.json
```

## 9. 오류 계약

모든 오류는 공통 Envelope를 사용한다.

```json
{
  "contractVersion": "1.0",
  "analysisId": null,
  "code": "INVALID_REQUEST",
  "message": "요청 형식이 올바르지 않습니다.",
  "retryable": false,
  "details": []
}
```

오류 코드:

```text
INVALID_REQUEST
UNSUPPORTED_CONTRACT_VERSION
UNSUPPORTED_COMBINATION
EVIDENCE_BUDGET_EXCEEDED
INVALID_EVIDENCE_REFERENCE
LLM_RATE_LIMITED
LLM_TIMEOUT
LLM_OUTPUT_INVALID
INTERNAL_ERROR
```

필수 필드 누락, 존재하지 않는 참조, 깊이 위반 및 근거 없는 Recommendation은 warning으로 낮추지 않는다. 부분 항목을 제거해 성공 처리하지 않고 전체 오류를 반환한다.

## 10. 보안과 입력 제한

```text
README: 최대 256 KiB
일반 텍스트 파일: 최대 128 KiB
P0 요청 전체: 최대 2 MiB
바이너리·생성 코드·빌드 결과물: 제외
Secret: [REDACTED]
```

기본 제외:

```text
.git, node_modules, dist, build, target, out, coverage, .next,
vendor, .venv, __pycache__, .env, .env.*, *.pem, *.key,
credentials.*, secrets.*, application-local.*
```

- README, 코드, 커밋 및 사용자 입력은 untrusted data로 직렬화한다.
- 외부 입력의 지시문을 따르지 않는다.
- LLM 요청·응답 전문과 원문 전체를 운영 로그에 남기지 않는다.
- 로그에는 `analysisId`, 단계, 처리 시간, Evidence 수, 토큰 사용량, 오류 코드만 남긴다.

## 11. 목표 구조

```text
gitddo/
├── docs/contracts/
│   ├── README.md
│   ├── analysis-request.schema.json
│   ├── analysis-response.schema.json
│   ├── error-response.schema.json
│   └── fixtures/
└── ai/
    ├── app/schemas/
    │   ├── common.py
    │   ├── enums.py
    │   ├── evidence.py
    │   ├── claims.py
    │   ├── repository.py
    │   ├── request.py
    │   ├── response.py
    │   └── error.py
    ├── app/validators/
    │   ├── evidence_validator.py
    │   ├── depth_validator.py
    │   └── report_validator.py
    ├── scripts/export_contracts.py
    └── tests/
```

공용 Schema는 Pydantic에서 Draft 2020-12로 생성하고 직접 수정하지 않는다. Java DTO와 AI Pydantic은 동일 Schema와 Fixture로 검증한다.

## 12. 구현 순서

### Step 0. 기준선 확인

- [ ] 작업 트리와 기존 변경 확인
- [ ] 현재 pytest, Ruff, mypy 결과 기록
- [ ] 기존 구 계약 파일과 테스트 목록 확인

이 단계에서는 커밋하지 않는다.

### Step 1. 미확정 wire format 합의

공용 Schema 구현 전에 백엔드 정상 요청·응답·오류 Fixture로 다음을 확정한다.

- [ ] `GroundedItem` 필드, 필수 여부와 null 정책
- [ ] `repositoryRefs` 식별자 형식
- [ ] `portfolioStatements`의 depth/confidence/supportStatus 포함 여부
- [ ] `tokenUsage` 하위 필드
- [ ] `validationWarnings` 객체 구조
- [ ] 오류 `details` 구조, 정렬과 중복 규칙
- [ ] Evidence discriminator 필드와 `DECIMAL` 직렬화
- [ ] Snapshot SHA 대소문자와 hash algorithm 적용 범위
- [ ] 참여 기간 필수 여부와 날짜 선후 관계
- [ ] `BACKEND_DERIVED.sourceEvidenceRefs` 최소 개수와 미관찰 표현

미합의 항목은 임의로 구현하지 않는다.

### Step 2. 공용 계약 문서

- [ ] `docs/contracts/README.md` 작성
- [ ] enum, Evidence/UserClaim/ReportItem, 깊이, 오류, 보안 규칙 기록
- [ ] 백엔드와 정상·경계·실패 Fixture 형식 합의

권장 커밋: `docs: 평가 계약 v1.0 설계 반영`

### Step 3. Pydantic 계약 교체

- [ ] 공통 enum과 제약 타입 구현
- [ ] Evidence discriminator 모델 구현
- [ ] UserClaim과 Snapshot 모델 구현
- [ ] UUID 요청 모델 구현
- [ ] GroundedItem, ReportItem 및 전체 응답 구현
- [ ] Error Envelope 구현
- [ ] 구 계약 테스트 교체

제거 대상:

```text
구 공통 버전 필드
정수 analysisId
구 단일 GitHub Evidence 타입
사용자 진술을 Evidence로 표현한 타입
AI 추천을 Evidence로 표현한 타입
구 AnalysisPurpose 4종
문자열 portfolioStatements
```

권장 커밋: `feat: 평가 API 계약 v1.0 재설계`

### Step 4. JSON Schema와 Fixture

- [ ] `docs/contracts/fixtures/` 작성
- [ ] `ai/scripts/export_contracts.py` 작성
- [ ] Request·Response·Error Draft 2020-12 Schema 생성
- [ ] 정상 Fixture 성공과 실패 Fixture 실패 검증
- [ ] Schema 재생성 무차이 테스트

권장 커밋: `build: 평가 계약 JSON Schema 생성 체계 추가`

### Step 5. 요청 의미 검증

- [ ] Evidence/Claim ID 전역 중복 검출
- [ ] 참조 존재와 Snapshot 관계 검증
- [ ] Evidence valueType/value 일치 검증
- [ ] completedEvidenceLevels 일치 검증
- [ ] MVP 지원 조합 검증

권장 커밋: `feat: 평가 요청 의미 검증 추가`

### Step 6. 응답 검증

- [ ] Repository/Evidence/Claim allowlist 검증
- [ ] 저장소별 깊이 검증
- [ ] ReportItem 참조 규칙 검증
- [ ] Recommendation Evidence 필수 검증
- [ ] `jobAppeal`과 `portfolioStatements` 규칙 검증
- [ ] 응답 전체 Item ID 중복 검출
- [ ] 치명적 위반 전체 실패 처리

권장 커밋: `feat: 리포트 근거 및 분석 깊이 검증 추가`

### Step 7. Mock 내부 API

- [ ] `POST /internal/v1/portfolio-reports` 구현
- [ ] Request validator → 고정 Fixture → Response validator 연결
- [ ] Error Envelope와 HTTP 상태 매핑
- [ ] Repository 1개·5개와 실패 케이스 테스트

권장 커밋: `feat: 평가 리포트 Mock API 구현`

### Step 8. 보안 경계

- [ ] 2 MiB 요청 제한
- [ ] untrusted data Prompt 경계
- [ ] Prompt Injection 무시
- [ ] 원문 로그와 Secret 노출 방지

권장 커밋: `feat: 평가 요청 보안 및 크기 제한 적용`

### Step 9. Gemini와 실제 리포트

Mock 계약과 양쪽 통합이 성공한 뒤 진행한다.

- [ ] Provider 인터페이스와 Gemini 구현
- [ ] Structured Output 연결
- [ ] 제한적인 429/timeout/5xx 재시도
- [ ] P0 Criteria와 Prompt 구현
- [ ] 생성 결과 검증 및 필요 시 1회 재생성
- [ ] 품질 Fixture 평가

LLM 연동 전에 계약·Mock·Validator가 완료되어야 한다.

## 13. 검증 명령

```bash
cd ai
pytest
ruff check .
ruff format --check .
mypy app
docker build -t gitddo-ai .
```

계약 변경 시 추가 확인:

- Pydantic serialization과 camelCase 계약 일치
- Schema 재생성 후 예상하지 않은 diff 없음
- 공용 정상 Fixture Schema 통과
- 공용 실패 Fixture의 예상 규칙 위반
- 미지원 조합의 `UNSUPPORTED_COMBINATION` 변환

## 14. 완료 기준

- [ ] 백엔드와 AI가 동일 JSON Schema와 Fixture를 사용한다.
- [ ] Evidence, UserClaim, ReportItem이 분리된다.
- [ ] UUID와 전역 ID 규칙이 적용된다.
- [ ] P0 Evidence와 판단 범위를 넘는 결과를 차단한다.
- [ ] 모든 Recommendation과 `jobAppeal`이 Evidence를 참조한다.
- [ ] 모든 포트폴리오 문장이 Evidence 또는 Claim을 참조한다.
- [ ] 저장소별 실제 분석 깊이와 limitations를 반환한다.
- [ ] 모든 오류가 Error Envelope를 사용한다.
- [ ] AI 서버가 stateless로 동작한다.
- [ ] Spring Boot의 최종 검증과 저장 흐름이 통합 테스트를 통과한다.
- [ ] pytest, Ruff, mypy, Docker 검증이 통과한다.

## 15. 중단 조건

다음 상황에서는 임의로 결정하지 않고 현재 문서, 구현, 선택지와 영향을 보고한다.

- 백엔드 DTO 또는 Fixture가 최종 가이드와 다름
- 미확정 wire field를 구현해야 함
- AI 서버에 DB, Redis, Job Lock 또는 결과 저장 책임이 요구됨
- P0 요청에 P1/P2 Evidence 또는 전체 코드가 포함됨
- JSON Schema와 Pydantic이 다름
- 계약 의미 변경 없이는 테스트를 통과할 수 없음
