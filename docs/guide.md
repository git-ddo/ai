# AI 서버 개발 가이드

이 문서는 최종 평가 계약을 구현하기 위한 작업 순서와 완료 조건을 정리한다. 계약의 전체 의미와 세부 제한은 루트 [`EVALUATION_CONTRACT_MIGRATION_GUIDE.md`](../EVALUATION_CONTRACT_MIGRATION_GUIDE.md)를 기준으로 한다.

## 1. 목표와 현재 상태

목표는 Spring Boot가 전달한 Evidence와 UserClaim을 바탕으로 근거가 연결된 포트폴리오 코칭 리포트를 생성하는 stateless FastAPI 서버를 구현하는 것이다.

현재 상태:

- [x] FastAPI 기반 환경 구성
- [x] `/health` 구현
- [x] pytest, Ruff, mypy, Docker 기반 구성
- [x] 양쪽 독립 개발에 필요한 계약 의미와 책임 경계 확정
- [ ] AI P0 Criteria·System Prompt·Gemini Provider 독립 구현
- [ ] 백엔드 P0 수집·Evidence 생성 독립 구현
- [ ] AI 내부 분석 파이프라인과 독립 테스트 구현
- [ ] 실제 사용 데이터를 기준으로 최종 Pydantic 계약 구현
- [ ] 공용 JSON Schema와 Fixture 생성
- [ ] 의미·참조·분석 깊이 Validator 구현
- [ ] Mock 연동 후 실제 E2E 연동

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

공용 Schema는 최종 DTO를 확정한 뒤 Pydantic에서 Draft 2020-12로 생성하고 직접 수정하지 않는다. Java DTO와 AI Pydantic은 동일 Schema와 Fixture로 검증한다.

## 12. 구현 순서

백엔드와 AI는 실제 HTTP 연동을 최대한 뒤로 미루고 각자의 핵심 기능을 Fake·Stub·내부 모델로 먼저 완성한다. 상세 wire DTO는 양쪽에서 실제 사용하는 데이터가 드러난 뒤 확정한다.

### Phase 0. 최소 공통 기준과 기준선

- [x] `BACKEND × ENTRY × PORTFOLIO_ANALYSIS × P0` 확정
- [x] Evidence, UserClaim, ReportItem 의미 분리
- [x] AI stateless와 Spring Boot Job·저장 책임 확정
- [x] Recommendation·`jobAppeal`·`portfolioStatements` 근거 원칙 확정
- [ ] 작업 시작 시 현재 pytest, Ruff, mypy 결과 기록
- [ ] 기존 구 계약 파일과 테스트 목록 확인

이 Phase에서는 세부 DTO와 Fixture를 확정하지 않는다.

### Phase 1. AI 독립 기반 개발

#### 1A. Backend P0 Criteria

- [ ] `ai/app/criteria/backend.yaml` 작성
- [ ] Criteria Loader 구현
- [ ] YAML 필수 필드와 허용값 검증
- [ ] P0에서 허용되는 README·기술 근거·테스트·Docker·CI 기준만 포함
- [ ] 설계 품질·코드 품질·사용자 역량 기준 제외

권장 커밋: `feat: Backend P0 Criteria 추가`

#### 1B. System Prompt

- [ ] Evidence와 UserClaim 분리 규칙 작성
- [ ] Repository 입력을 untrusted data로 격리
- [ ] README·코드·사용자 입력의 지시문 무시
- [ ] 입력에 없는 사실 생성 금지
- [ ] P0 범위 초과 판단 금지
- [ ] 기여율·실력·취업 가능성 단정 금지
- [ ] `NOT_OBSERVED` 의미 보호
- [ ] Prompt 단위 테스트 작성

최종 응답 필드명과 JSON Schema 지시는 계약 확정 후 추가한다.

권장 커밋: `feat: 근거 기반 System Prompt 추가`

#### 1C. Gemini Provider 기반

- [ ] `LLMProvider` 인터페이스 정의
- [ ] Gemini 클라이언트 초기화
- [ ] API key와 모델명 환경변수화
- [ ] timeout과 429·5xx 제한적 retry
- [ ] provider 오류를 내부 예외로 변환
- [ ] 작은 테스트용 Pydantic 출력 모델로 Structured Output 검증
- [ ] 실제 API에 의존하지 않는 Fake Provider 테스트

최종 `PortfolioReport` DTO, Evidence Validator와 서비스 연결은 이 Phase에서 구현하지 않는다.

권장 커밋: `feat: Gemini Provider 기반 구현`

### Phase 2. 백엔드 독립 P0 개발

이 Phase는 Spring Boot 팀의 독립 작업 범위이다. AI 서버를 실행하지 않고 Fake AI Client로 검증한다.

- [ ] Repository 메타데이터와 default branch 수집
- [ ] Snapshot SHA 고정
- [ ] README, 파일 트리, dependency, 테스트, Docker, Actions 수집
- [ ] `GITHUB_STATIC`, `BACKEND_DERIVED` Evidence 생성
- [ ] Evidence ID, `contentHash`, Repository·Snapshot 연결
- [ ] `README_SECTION_MISSING`, `TEST_NOT_OBSERVED`, `DEPLOYMENT_CONFIG_NOT_OBSERVED` 생성
- [ ] Secret, 바이너리, 생성 파일, 대용량 파일 제거
- [ ] Evaluation Job과 실패·재시도 흐름 구현
- [ ] Fake AI Client로 결과 저장 흐름 검증

### Phase 3. AI 내부 분석 파이프라인

최종 HTTP DTO 대신 AI 전용 내부 모델과 독립 Fixture를 사용한다.

```text
내부 테스트 입력
→ 정규화
→ P0 Criteria 선택
→ Prompt 생성
→ Fake 또는 Gemini Provider
→ Repository별 분석
→ Portfolio 종합
→ 정책 검증
```

- [ ] `normalization_service.py` 구현
- [ ] `repository_service.py` 구현
- [ ] `portfolio_service.py` 구현
- [ ] `report_service.py` 오케스트레이션 구현
- [ ] Repository별 요약·어필 후보·보완 후보 생성
- [ ] 전체 진단·대표 프로젝트·면접 소재·문장 후보 생성
- [ ] P0 범위 초과 및 금지 표현 검사
- [ ] Provider를 Fake로 교체할 수 있는 의존성 주입

내부 모델은 최종 wire DTO와 분리한다. 이후 API DTO가 변경되어도 변환 계층만 수정할 수 있어야 한다.

권장 커밋: `feat: P0 포트폴리오 분석 파이프라인 추가`

### Phase 4. 양쪽 독립 검증

AI 검증:

- [ ] Criteria Loader 정상·실패 테스트
- [ ] Prompt Injection 테스트
- [ ] Gemini timeout·rate limit·잘못된 출력 테스트
- [ ] P0 범위 초과 응답 차단
- [ ] 입력에 없는 기술·파일 생성 방지
- [ ] 내부 Repository 1개·5개 분석 테스트

백엔드 검증:

- [ ] Snapshot 재현성과 SHA 연결
- [ ] Evidence 생성 및 누락 기반 Evidence 규칙
- [ ] Secret 제거와 입력 예산
- [ ] Repository 1개·5개 수집
- [ ] Job 실패·재시도·중복 결과 정책

### Phase 5. 최종 DTO·Schema·Fixture 확정

양쪽 독립 개발에서 확인된 실제 데이터를 모아 wire contract를 확정한다.

순서:

1. 백엔드 P0 Evidence 출력 확인
2. AI 내부 입력·출력 모델과 비교
3. 미확정 wire format 합의
4. Request·Response·Error Pydantic 구현
5. Java DTO 구현
6. Pydantic에서 Draft 2020-12 JSON Schema 생성
7. 정상·경계·실패 공용 Fixture 작성
8. 양쪽 Schema·Fixture 테스트

확정 대상:

- [ ] `GroundedItem` 필드, 필수 여부와 null 정책
- [ ] `repositoryRefs` 식별자 형식
- [ ] `portfolioStatements`의 depth/confidence/supportStatus 포함 여부
- [ ] `tokenUsage` 하위 필드
- [ ] `validationWarnings` 객체 구조
- [ ] 오류 `details` 구조, 정렬과 중복 규칙
- [ ] Evidence discriminator와 `DECIMAL` 직렬화
- [ ] Snapshot SHA 대소문자와 hash algorithm 적용 범위
- [ ] 참여 기간 필수 여부와 날짜 선후 관계
- [ ] `BACKEND_DERIVED.sourceEvidenceRefs` 최소 개수와 미관찰 표현

Fixture 선확정은 요구하지 않는다. Pydantic과 Java DTO의 의미를 합의한 뒤 Fixture를 생성한다.

권장 커밋:

```text
docs: 평가 계약 v1.0 wire format 확정
feat: 평가 API 계약 v1.0 재설계
build: 평가 계약 JSON Schema와 Fixture 추가
```

### Phase 6. 계약 Validator

AI 서버:

- [ ] Evidence·Claim ID 전역 유일성
- [ ] 참조 존재와 Repository·Snapshot 관계
- [ ] Evidence valueType/value 일치
- [ ] 저장소별 `completedEvidenceLevels`
- [ ] MVP 지원 조합
- [ ] ReportItem 참조 규칙
- [ ] Recommendation Evidence 필수
- [ ] `jobAppeal` Claim 단독 금지
- [ ] `portfolioStatements` 참조 필수
- [ ] 응답 전체 Item ID 중복
- [ ] 치명적 위반 전체 실패 처리

Spring Boot:

- [ ] Response JSON Schema 검증
- [ ] `analysisId`, Repository, Snapshot 일치
- [ ] Evidence·Claim allowlist
- [ ] 저장소별 분석 깊이
- [ ] 최초 검증 성공 결과만 저장

### Phase 7. Mock 연동

실제 Gemini 분석 대신 계약과 전송 흐름만 확인한다.

```text
Spring Boot P0 Evidence
→ 실제 Request DTO
→ POST /internal/v1/portfolio-reports
→ FastAPI 고정 Response Fixture
→ Spring Boot 최종 검증·저장
```

- [ ] Repository 1개·5개
- [ ] 지원하지 않는 조합
- [ ] HTTP 상태와 Error Envelope
- [ ] 요청 크기와 timeout
- [ ] 잘못된 참조·Snapshot·깊이
- [ ] Spring Boot 재호출과 중복 결과 저장 방지

권장 커밋: `feat: 평가 리포트 Mock API 구현`

### Phase 8. 실제 연동과 E2E

```text
Spring Boot P0 Collector
→ Request DTO
→ FastAPI
→ Criteria + Prompt + Gemini
→ AI Validator
→ Response DTO
→ Spring Boot 최종 검증·저장
```

진행 순서:

1. Repository 1개 정상 요청
2. Evidence가 부족한 Repository
3. Repository 5개
4. Gemini timeout·rate limit
5. 잘못된 Structured Output
6. 동일 요청 재호출과 중복 LLM 실행
7. 전체 E2E와 운영 로그 점검

이 Phase 전까지 백엔드와 AI는 서로의 실행 환경에 의존하지 않아야 한다.

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
