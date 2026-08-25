# AI 서버 개발 가이드

## 1. 문서 역할

이 문서는 GitDdo AI 서버의 현재 상태, 다음 구현 순서와 단계별 완료 조건을 설명한다.
P0/P1/P2 의미와 정책은 루트
[`EVALUATION_CONTRACT_MIGRATION_GUIDE.md`](../EVALUATION_CONTRACT_MIGRATION_GUIDE.md)를 따른다.

Wire request·response·error 필드의 최종 Source of Truth는 Backend JSON Schema이다.

```text
backend/backend/docs/contracts/analysis-request.schema.json
backend/backend/docs/contracts/analysis-response.schema.json
backend/backend/docs/contracts/analysis-error.schema.json
```

Markdown과 Schema가 충돌하면 Backend Schema와 구현을 우선 확인한다. P2는 현재
`origin/feat/portfolio-evaluation-p2`의 `bcc9a4f`를 기준으로 임시 동기화했으며 Backend
`main` 병합 후 다시 점검한다.

## 2. 목표

Spring Boot가 전달한 Evidence와 UserClaim을 바탕으로 근거가 연결된 코칭 리포트를 생성하는
stateless FastAPI 서버를 구현한다.

개발 목표 조합:

```text
Repository: 1~5개
TargetJob: BACKEND
TargetCareerLevel: ENTRY
AnalysisPurpose: PORTFOLIO_ANALYSIS
RequestedAnalysisDepth: P0 | P1 | P2
schemaVersion: "1.0"
```

`FRONTEND`, `AI`, `CLOUD_INFRA`, `JUNIOR`, `MID`, `SENIOR`는 Schema에서 표현 가능하지만 현재
분석 Criteria와 Prompt 구현 범위가 아니다.

## 3. 현재 상태

### Backend

- [x] P0 수집과 Evidence Snapshot
- [x] P1 커밋·PR·변경 경로 수집
- [x] Mock AI Client, 응답 Validator와 Job 저장 흐름
- [ ] P2 코드 snippet Collector `main` 병합
- [ ] P2 전역 snippet/token 예산
- [ ] AI HTTP connect 5초·read 300초 timeout 적용

### AI

- [x] FastAPI 환경과 `/health`
- [x] pytest, Ruff, mypy, Docker 구성
- [x] Backend P0/P1/P2 Criteria·필수 key allowlist·누적 Loader
- [x] 근거 기반 P0/P1/P2 혼합 깊이 System Prompt
- [x] Gemini Structured Output Provider와 Fake Provider
- [x] HTTP DTO와 분리된 P0/P1/P2 내부 Evidence 모델
- [x] 분석 전체 Evidence·Claim ID 중복 검증
- [x] P0/P1/P2 입력 정규화
- [x] P0/P1/P2 깊이별 Repository·Portfolio·Interview Prompt Context
- [x] Prompt 예약 마커 충돌 방지
- [x] 정책 위반 타입과 `ReportPolicyError`
- [x] Repository Evidence·Claim 참조 Validator
- [x] P1/P2 내부 Evidence 모델
- [x] P1/P2 Criteria
- [x] 입력 참조·분석 깊이 Validator
- [x] Repository 생성 결과의 Criteria·기술·파일 grounding 메타데이터
- [x] Repository 생성 결과 내용 정책 Validator
- [x] Repository 분석 Service와 정책 실패 1회 재생성
- [x] Portfolio 전체 범위 참조·혼합 깊이·내용 정책 Validator
- [x] Portfolio synthesis 생성과 정책 실패 1회 재생성 Service
- [x] InterviewQuestion·PortfolioStatement grounding 내부 모델과 Batch
- [x] InterviewQuestion·PortfolioStatement 참조·깊이·내용 정책 Validator
- [x] InterviewQuestion 생성과 정책 실패 1회 재생성 Service
- [x] PortfolioStatement 생성과 정책 실패 1회 재생성 Service
- [x] 검증 완료 결과의 결정적 `PortfolioAnalysis` 최종 조립
- [x] Report Service와 내부 전체 오케스트레이션
- [ ] Backend Schema 기준 Pydantic Wire DTO
- [ ] `POST /internal/v1/portfolio-reports`
- [ ] Spring Boot Mock 및 실제 Gemini E2E

현재 AI 검증 기준은 전체 `pytest` 841개와 Ruff·mypy 통과이다. 이는 실제 Gemini 호출과 Wire
API를 포함하지 않는다.

## 4. 아키텍처 경계

```text
Frontend
  평가 생성 · 상태/결과 조회
        ↓
Spring Boot
  Snapshot 고정
  → P0/P1/P2 Evidence 수집
  → UserClaim 구성
  → request 조립
        ↓ POST /internal/v1/portfolio-reports
FastAPI
  Pydantic/의미 검증
  → Repository별 완료 깊이 확인
  → Criteria/Prompt 선택
  → Gemini Structured Output
  → 참조/깊이/내용 정책 검증
        ↓
Spring Boot
  최종 검증
  → 결과 저장 또는 Job FAILED
```

AI 서버는 GitHub API, 사용자 인증, Snapshot, Evaluation Job, DB 저장과 멱등성 정책을 관리하지
않는다.

## 5. 분석 깊이 처리

| 깊이 | Evidence | AI 허용 범위 |
| --- | --- | --- |
| P0 | `GITHUB_STATIC`, P0 `BACKEND_DERIVED` | 문서·구조·설정의 관찰 여부 |
| P1 | `GITHUB_ACTIVITY`, P1 `BACKEND_DERIVED` | 관찰된 활동·변경 영역과 Claim 연결 후보 |
| P2 | `CODE_EVIDENCE`, P2 `BACKEND_DERIVED` | 제공된 코드 구간의 검증·오류 처리·책임과 테스트 사례 |

`requestedAnalysisDepth`는 요청 전체의 최대 목표이다. 실제 판단은 각 Repository의
`completedEvidenceLevels`를 기준으로 한다.

```text
requestedAnalysisDepth=P2
Repo A=[P0,P1,P2]
Repo B=[P0,P1]
Repo C=[P0]
```

Repo B와 Repo C에 P2 판단을 생성하면 전체 리포트 실패이다.

## 6. 현재 Wire 계약 요약

문서에는 대형 JSON을 복제하지 않는다. 주요 필드만 다음과 같이 이해한다.

### Request

```text
schemaVersion
analysisId
targetJob
targetCareerLevel
analysisPurpose
requestedAnalysisDepth
extractorVersion
repositories[]
```

Repository:

```text
repositoryId (string)
repositoryFullName
defaultBranch
snapshotHashAlgorithm
snapshotSha
completedEvidenceLevels
collectionWarnings
userClaims
evidence
```

P2 Evidence는 `value`에 snippet을 담고 `path`, `startLine`, `endLine`, `commitSha`,
`pullRequestNumber`, `sourceEvidenceRefs`를 사용한다. `contentHash`와 `language`는 현재 Wire
필드가 아니다.

### Response

```text
schemaVersion
analysisId
evaluatorVersion
requestedAnalysisDepth
usedEvidenceLevels
summary
repositories[].findings[]
coaching
limitations
```

현재 `jobAppeal`은 단일 객체이다. `portfolioStatements`와 `interviewQuestions`에는
`repositoryId`가 없으며, 문장 `type`과 `followUpQuestions`도 없다. Backend Schema가 변경되기
전 AI Wire DTO에 임의로 추가하지 않는다.

### Error

```text
schemaVersion
analysisId
code
message
retryable
details (object)
```

## 7. 보안과 실패 정책

- Repository 데이터, README, 코드, 활동과 UserClaim은 untrusted data이다.
- 외부 데이터의 지시문을 따르지 않는다.
- 입력에 없는 기술, 파일, 기능을 생성하지 않는다.
- 코드를 실행하지 않는다.
- Prompt·응답 전문과 민감 원문을 로그에 남기지 않는다.
- 잘못된 일부 항목을 제거해 성공으로 반환하지 않는다.
- Repository 하나라도 필수 분석·검증에 실패하면 전체 분석을 실패시킨다.

Retry:

```text
Gemini Provider: 429, timeout, 5xx 제한적 retry
AI 최종 실패: Error Envelope
Backend: 자동 재호출 없이 Job FAILED
```

Timeout 계약:

```text
Backend Connect: 5초
AI 전체 Deadline: 270초
Backend Read: 300초
```

현재 Gemini 개별 호출 timeout은 존재하지만 전체 270초 deadline은 후속 구현 대상이다.

## 8. 구현 순서

한 단계는 독립 테스트와 하나의 논리적 커밋을 만들 수 있는 크기로 제한한다.

### Phase 1. P1/P2 내부 Evidence 도메인 모델

대상:

```text
ai/app/domain/enums.py
ai/app/domain/models.py
ai/tests/test_domain_models.py
```

구현:

- [x] `AnalysisDepth`에 P1/P2 추가
- [x] `InternalEvidenceType`에 `GITHUB_ACTIVITY`, `CODE_EVIDENCE` 추가
- [x] `repository_id`를 Backend와 같은 문자열 표현으로 전환
- [x] `completed_evidence_levels` 추가
- [x] Wire `factKey`·`value`에 대응하는 내부 `key`·`summary`와 `value_type` 확장
- [x] `path`, `start_line`, `end_line` 추가
- [x] `commit_sha`, `pull_request_number`, `source_evidence_refs` 추가
- [x] Evidence 타입·깊이 조합 검증
- [x] P2 line range와 source Evidence 구조 검증
- [x] 혼합 깊이 Repository 1~5개 테스트

완료 기준:

- P0 기존 입력이 계속 통과한다.
- P1/P2 필수 메타데이터가 없으면 거절한다.
- Repository·Evidence·Claim ID 전역 중복 검증이 유지된다.

### Phase 2. P1/P2 Criteria와 Loader

대상:

```text
ai/app/criteria/backend.yaml
ai/app/criteria/backend_p1.yaml
ai/app/criteria/backend_p2.yaml
ai/app/criteria/models.py
ai/app/criteria/loader.py
ai/tests/test_criteria_loader.py
```

구현:

- [x] P0 Criteria 유지
- [x] P1 활동·Claim 연결 기준 추가
- [x] P2 snippet 범위 판단 기준 추가
- [x] 깊이별 고정 파일 mapping
- [x] P2 요청 시 P0→P1→P2 Criteria 누적 로드
- [x] 기계 판독 가능한 깊이별 금지 판단 guardrail 검증

P1 Criteria는 활동을 실력·기여율로 평가하지 않는다. P2 Criteria는 snippet을 Repository 전체
품질로 일반화하지 않는다.

### Phase 3. 혼합 깊이 System Prompt

대상:

```text
ai/app/prompts/system.py
ai/tests/test_system_prompt.py
```

구현:

- [x] Repository별 `completedEvidenceLevels` 준수
- [x] P1 활동량의 실력·기여율 해석 금지
- [x] P2 snippet의 Repository 전체 일반화 금지
- [x] 코드 실행과 입력 밖 코드·기술 생성 금지
- [x] P0/P1/P2 판단 범위 명시
- [x] Prompt 버전 갱신

System Prompt는 외부 데이터를 인자로 받지 않는 고정 정책을 유지한다.

### Phase 4. P1/P2 정규화와 Prompt Context

대상:

```text
ai/app/domain/models.py
ai/app/services/normalization_service.py
ai/app/prompts/context.py
ai/app/prompts/repository.py
ai/app/prompts/portfolio.py
ai/app/prompts/interview.py
ai/tests/test_domain_models.py
ai/tests/test_normalization.py
ai/tests/test_prompt_context.py
```

구현:

- [x] P1/P2 Evidence 보존과 경로 정규화
- [x] line range·commit SHA·PR number 보존
- [x] `sourceEvidenceRefs` 보존
- [x] P0/P1/P2 data block 분리
- [x] code snippet도 untrusted JSON으로 직렬화
- [x] 기존 예약 마커 escape 회귀 테스트

정규화 단계에서 새로운 기술·활동·사실을 추론하지 않는다.

### Phase 5. 입력 참조·깊이 Validator

대상:

```text
ai/app/validators/evidence_validator.py
ai/app/validators/depth_validator.py
ai/tests/test_evidence_validator.py
ai/tests/test_depth_validator.py
```

구현:

- [x] Evidence·Claim ID 전역 유일성
- [x] Repository 구성원 소유 관계와 Repository Snapshot 존재 검증
- [x] `sourceEvidenceRefs`, `relatedEvidenceRefs` 존재 검증
- [x] 교차 Repository 참조 금지
- [x] 요청 최대 깊이와 Repository별 완료 깊이 분리
- [x] P0/P1/P2 타입·깊이 조합 검증
- [x] `completedEvidenceLevels`와 실제 Evidence 일치
- [x] P2 snippet 필수 메타데이터와 P1 source 검증
- [x] 참조 순환과 상향 깊이 파생 방지

입력 Reference Validator는 Backend가 전달한 Evidence·UserClaim 그래프를 LLM 호출 전에
검증한다. 기존 Repository Policy Validator는 LLM이 생성한 결과의 참조를 검증하므로 책임이
다르다. 내부 `requested_analysis_depth`는 요청 전체의 최대 깊이이고 Repository의
`analysis_depth`는 해당 Repository가 실제 완료한 최대 깊이이다.

현재 내부 Evidence는 Wire의 Evidence별 `repositoryId`·`snapshotSha`를 보존하지 않는다. 따라서
Evidence별 Repository·Snapshot 값이 부모와 같은지는 향후 Wire DTO → 내부 모델 Mapper에서
검증한다. 이번 단계에서는 Repository Snapshot 필수 여부와 내부 구성원의 Repository 소유
관계까지만 검증한다.

### Phase 6. Repository 분석과 내용 정책 Validator

대상:

```text
ai/app/services/repository_service.py
ai/app/validators/report_validator.py
ai/tests/test_repository_service.py
ai/tests/test_report_policy_validator.py
```

흐름:

```text
NormalizedRepositoryContext
→ 누적 Criteria
→ Repository Prompt
→ LLMProvider
→ RepositoryAnalysis
→ 참조·깊이·내용 정책 검증
```

구현:

- [x] 각 항목의 Criteria key·기술명·파일 경로 grounding 메타데이터
- [x] Criteria 깊이·Evidence 타입·UserClaim 허용 정책 검증
- [x] 입력 기술·Evidence 경로 allowlist 검증
- [x] P0 품질·역량·기여 단정 검출
- [x] P1 활동량 기반 기여율·실력 단정 검출
- [x] P2 snippet의 Repository 전체 일반화 검출
- [x] UserClaim 사실 승격과 `NOT_OBSERVED` 오용 검출
- [x] 누락 Recommendation의 명시적 `BACKEND_DERIVED` Evidence 검증
- [x] Repository별 독립 생성
- [x] Evidence·Claim 참조 검증 연결
- [x] 최초 정책 실패 시 최대 1회 재생성
- [x] 재검증 실패 시 전체 Repository 분석 오류

내용 정책 Validator는 순수 Python 규칙으로 동작한다. 기술명·파일 경로·Criteria는 구조화된
메타데이터를 allowlist와 비교해 결정적으로 검증한다. 자연어 단정 검출은 보수적인 고정 패턴을
사용하므로 모든 표현을 완전하게 판별하는 장치는 아니며 Prompt 제한과 Service의 1회 재생성을
함께 사용한다.

`RepositoryAnalysisService`는 Gemini 구현체가 아니라 `LLMProvider`에 의존한다. Provider의
429·timeout·5xx retry와 생성 결과 정책 재생성은 별도 흐름이다. 정책 재생성 Prompt에는 이전
응답이나 위반 메시지를 넣지 않고 중복을 제거한 위반 코드만 추가하며, 두 Provider 호출이
성공하면 `duration_ms`와 `attempt_count`를 합산한다. 두 번째 정책 검증 실패 시 마지막
`ReportPolicyError`를 그대로 반환한다.

### Phase 7. Portfolio·Interview·Statement 생성

대상:

```text
ai/app/services/portfolio_service.py
ai/app/services/analysis_service.py
ai/app/prompts/portfolio.py
ai/app/prompts/interview.py
ai/tests/test_portfolio_service.py
ai/tests/test_analysis_service.py
```

구현:

- [x] `PortfolioSynthesis` Structured Output과 최종 `PortfolioAnalysis` 조립 책임 분리
- [x] 전체 요약·대표 Repository·strengths/gaps/nextActions·단일 `jobAppeal` 모델
- [x] Portfolio Prompt의 생성·제외 필드와 혼합 깊이 제약
- [x] Portfolio 전체 범위 참조·깊이·내용 정책 Validator
- [x] Portfolio synthesis 생성과 정책 재생성 Service
- [x] `InterviewQuestion`·`PortfolioStatement` grounding 필드와 Batch 내부 모델
- [x] InterviewQuestion·PortfolioStatement 참조·깊이·내용 정책 Validator
- [x] InterviewQuestion 생성과 정책 실패 1회 재생성 Service
- [x] PortfolioStatement 생성과 정책 실패 1회 재생성 Service
- [x] PortfolioAnalysis 최종 조립

Portfolio LLM 호출은 기존 `RepositoryAnalysis`를 다시 생성하지 않고, 종합 결과인
`PortfolioSynthesis`만 Structured Output으로 생성한다. `PortfolioAnalysis`는 Assembler에서
Repository 분석, synthesis, 면접 질문과 포트폴리오 문장을 조립한 최종 내부 결과이다.

Portfolio Validator는 전체 요약·strengths·gaps·nextActions·jobAppeal의 다중 Repository
참조를 허용하고, 대표 Repository 참조는 해당 Repository 범위로 제한한다. Criteria와
Evidence는 각 소유 Repository의 실제 완료 깊이에 맞춰 검증한다. 하나의 항목이 서로 다른
깊이의 Repository를 함께 참조하면 자연어 내용 정책은 가장 얕은 깊이를 상한으로 적용한다.
누락 gap·nextAction은 대상 Repository와 일치하는 명시적 `BACKEND_DERIVED` Evidence가
필요하다. 이 Validator는 결과를 수정하지 않고 위반을 모아 `ReportPolicyError`를 발생시킨다.

Portfolio synthesis Service는 가장 깊은 Repository에 맞는 누적 Criteria를 로드하고
`PortfolioSynthesis`만 Structured Output으로 생성한다. 참조·내용 정책 실패 시 위반 코드만
담은 교정 Prompt로 전체 synthesis를 한 번 재생성한다. Provider retry와 정책 재생성은 별도
흐름이며, 재생성 성공 시 두 호출의 `duration_ms`와 `attempt_count`를 합산한다.

InterviewQuestion Service는 Repository Context와 기존 `RepositoryAnalysis`를 기반으로
`InterviewQuestionBatch`를 생성한다. 대상 Repository 참조를 먼저 검증하고 Criteria·기술·파일과
자연어 내용을 이어서 검증한다. 최초 결과가 정책 위반인 경우에만 위반 코드만 담은 교정 Prompt로
전체 Batch를 한 번 재생성하며, Provider 오류와 입력·Prompt·Criteria 오류는 재생성하지 않는다.

PortfolioStatement Service는 Repository Context, Repository별 분석과 `PortfolioSynthesis`를
기반으로 `PortfolioStatementBatch`를 생성한다. 전체 Context 중 가장 깊은 수준의 누적 Criteria를
사용하되 각 문장의 실제 판단 상한은 참조 Repository 중 가장 얕은 완료 깊이이다. 참조·내용 정책
위반에만 위반 코드 기반 전체 Batch 재생성을 한 번 허용하고 Provider 오류는 그대로 전파한다.

PortfolioAnalysis Assembler는 Context 입력 순서에 맞춰 Repository 분석과 Interview Batch를
결정적으로 배치하고, Statement 순서를 그대로 유지한다. 조립 전 Repository별 실제 깊이 Criteria와
전체 최대 깊이 Criteria를 선택해 네 결과 종류의 참조·내용 정책을 다시 검증한다. 이 단계는 LLM을
호출하거나 결과를 수정하지 않으며, Provider 메타데이터와 generation record 조립은 Phase 8에 남긴다.

현재 Wire에 없는 문장 `type`, 문장·질문의 `repositoryId`, `followUpQuestions`는 내부 모델에
있더라도 Wire 변환 전에 Backend 계약 상태를 다시 확인한다.

### Phase 8. Report Service와 전체 Deadline

대상:

```text
ai/app/services/report_service.py
ai/tests/test_report_service.py
```

흐름:

```text
InternalPortfolioInput
→ Evidence 참조·분석 깊이 검증
→ Repository별 정규화
→ RepositoryAnalysisService (Context 순서, 1~5개)
→ PortfolioSynthesisService (1회)
→ InterviewQuestionService (대상 Repository별)
→ PortfolioStatementService (1회)
→ PortfolioAnalysisAssembler
→ generation metadata 집계
→ InternalPortfolioReport
```

구현:

- [x] `LLMProvider` 의존성 주입
- [x] 기존 Input Validator·Normalization·생성 Service·Assembler 조합
- [x] Repository 1~5개 처리
- [x] 혼합 깊이 처리
- [x] Repository 하나 실패 시 전체 실패
- [x] 모든 Gemini 호출·retry를 포함한 270초 전체 deadline
- [x] 단계별 처리 시간과 시도 횟수 집계

Report Service는 새로운 분석 문장이나 Criteria를 직접 만들지 않는다. 각 하위 Service가 반환한
`StructuredGeneration`의 `duration_ms`·`attempt_count`를 `InternalGenerationRecord`로 변환하고,
Assembler가 만든 `PortfolioAnalysis`와 합쳐 `InternalPortfolioReport`를 반환한다. Provider retry와
정책 위반 1회 재생성은 기존 하위 계층 책임을 유지하며, Report Service는 전체 deadline과 단계
순서, 전체 실패 정책만 관리한다.

`report_service.py`와 `test_report_service.py` 구현을 완료했다. 전체 파이프라인은 입력 순서를
보존해 순차 실행하며, 실패 시 부분 리포트를 반환하지 않는다.

### Phase 9. Backend Wire DTO와 Error Envelope

대상:

```text
ai/app/schemas/
ai/app/api/reports.py
ai/tests/test_request_schema.py
ai/tests/test_response_schema.py
ai/tests/test_api.py
```

구현:

- [ ] `schemaVersion="1.0"`
- [ ] 문자열 `repositoryId`
- [ ] `findingId`와 Backend category/severity
- [ ] Backend request·response·error Schema와 일치
- [ ] 내부 모델↔Wire DTO 변환
- [ ] Error Code별 HTTP status와 `retryable`
- [ ] `POST /internal/v1/portfolio-reports`
- [ ] 요청 크기와 민감 로그 제한

Backend Schema에 없는 필드를 임의로 추가하지 않는다.

현재 `ai/app/schemas/`와 `test_request_schema.py`·`test_response_schema.py`는 과거 계약 초안이다.
해당 테스트가 통과하는 것은 Backend 최종 JSON Schema 호환을 의미하지 않는다. Phase 9에서는
초안에 호환 레이어를 덧붙이지 않고 Backend Schema·Example을 기준으로 DTO와 Fixture를 교체한다.

### Phase 10. 독립 및 E2E 검증

최소 시나리오:

- [ ] P0 Repository
- [ ] P0+P1 Repository
- [ ] P0+P1+P2 Repository
- [ ] Repository별 깊이가 다른 요청
- [ ] Repository 1개와 5개
- [ ] UserClaim만 있고 공개 근거가 부족한 경우
- [ ] collection warning이 있는 경우
- [ ] Prompt Injection이 포함된 README·commit·code snippet
- [ ] 교차 Repository 참조
- [ ] 입력에 없는 기술·파일 생성
- [ ] P2 snippet을 Repository 전체로 일반화한 출력
- [ ] Gemini timeout·429·5xx·잘못된 Structured Output
- [ ] Backend Example JSON과 Pydantic 호환
- [ ] Spring Boot Mock·HTTP E2E

## 9. P2 구현 시 Backend 재확인 항목

P2 `main` 병합 전에 다음은 아직 최종 구현값이 아니다.

- 전체 요청 snippet 상한
- 전체 Evidence/token 예산
- P2 대상 Repository 최대 수
- 사용자 지정 파일·역할 경로·Production/Test 쌍 우선순위
- P2 snippet DB 보관 정책
- Warning→Limitation 변환
- 모든 Finding의 Evidence 최소 1개 강제
- 문장·질문의 Repository 범위

AI는 이러한 값을 임의로 만들어 Backend 계약처럼 구현하지 않는다.

## 10. 실행과 검증

AI 디렉터리에서 실행한다.

```bash
pytest
ruff check .
ruff format --check .
mypy app
docker build -t gitddo-ai .
```

단계별로 관련 단위 테스트를 먼저 실행한 뒤 전체 검증을 수행한다. 계약 변경은 Backend
Schema·Example과 Pydantic 간 일치 테스트를 추가한다.

## 11. 커밋 순서

권장 후속 커밋 순서는 다음과 같다.

```text
1. feat: P1/P2 내부 Evidence 모델 확장
2. feat: Backend P1/P2 Criteria 추가
3. feat: 혼합 깊이 근거 기반 Prompt 추가
4. feat: P1/P2 입력 정규화와 Context 추가
5. feat: Evidence 참조와 분석 깊이 검증 추가
6. feat: Repository P0/P1/P2 분석 서비스 추가
7. feat: Portfolio 코칭 생성 서비스 추가
8. feat: 전체 리포트 오케스트레이션 추가
9. feat: Backend 평가 Wire 계약 구현
10. feat: 포트폴리오 리포트 내부 API 추가
```

각 커밋은 관련 pytest, Ruff와 mypy를 통과한 뒤 생성한다. Push, branch 전환 또는 PR은 사용자
요청이 있을 때만 수행한다.
