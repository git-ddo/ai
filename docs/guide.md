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
- [x] Backend P0 Criteria·필수 key allowlist·Loader
- [x] 근거 기반 P0 System Prompt
- [x] Gemini Structured Output Provider와 Fake Provider
- [x] HTTP DTO와 분리된 P0/P1/P2 내부 Evidence 모델
- [x] 분석 전체 Evidence·Claim ID 중복 검증
- [x] P0 입력 정규화
- [x] Repository·Portfolio·Interview Prompt Context
- [x] Prompt 예약 마커 충돌 방지
- [x] 정책 위반 타입과 `ReportPolicyError`
- [x] Repository Evidence·Claim 참조 Validator
- [x] P1/P2 내부 Evidence 모델
- [ ] P1/P2 Criteria
- [ ] P1/P2 정규화·Prompt·깊이 Validator
- [ ] Repository·Portfolio·Report Service
- [ ] 내용 정책 Validator와 내부 전체 오케스트레이션
- [ ] Backend Schema 기준 Pydantic Wire DTO
- [ ] `POST /internal/v1/portfolio-reports`
- [ ] Spring Boot Mock 및 실제 Gemini E2E

현재 AI 검증 기준은 전체 `pytest` 353개와 Ruff·mypy 통과이다. 이는 실제 Gemini 호출,
P1/P2 분석과 Wire API를 포함하지 않는다.

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

- [ ] P0 Criteria 유지
- [ ] P1 활동·Claim 연결 기준 추가
- [ ] P2 snippet 범위 판단 기준 추가
- [ ] 깊이별 고정 파일 mapping
- [ ] P2 요청 시 P0→P1→P2 Criteria 누적 로드
- [ ] 금지 판단 allowlist 검증

P1 Criteria는 활동을 실력·기여율로 평가하지 않는다. P2 Criteria는 snippet을 Repository 전체
품질로 일반화하지 않는다.

### Phase 3. 혼합 깊이 System Prompt

대상:

```text
ai/app/prompts/system.py
ai/tests/test_system_prompt.py
```

구현:

- [ ] Repository별 `completedEvidenceLevels` 준수
- [ ] P1 활동량의 실력·기여율 해석 금지
- [ ] P2 snippet의 Repository 전체 일반화 금지
- [ ] 코드 실행과 입력 밖 코드·기술 생성 금지
- [ ] P0/P1/P2 판단 범위 명시
- [ ] Prompt 버전 갱신

System Prompt는 외부 데이터를 인자로 받지 않는 고정 정책을 유지한다.

### Phase 4. P1/P2 정규화와 Prompt Context

대상:

```text
ai/app/services/normalization_service.py
ai/app/prompts/context.py
ai/app/prompts/repository.py
ai/app/prompts/portfolio.py
ai/app/prompts/interview.py
ai/tests/test_normalization.py
ai/tests/test_prompt_context.py
```

구현:

- [ ] P1/P2 Evidence 보존과 경로 정규화
- [ ] line range·commit SHA·PR number 보존
- [ ] `sourceEvidenceRefs` 보존
- [ ] P0/P1/P2 data block 분리
- [ ] code snippet도 untrusted JSON으로 직렬화
- [ ] 기존 예약 마커 escape 회귀 테스트

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

- [ ] Evidence·Claim ID 전역 유일성
- [ ] Repository·Snapshot 소유 관계
- [ ] `sourceEvidenceRefs`, `relatedEvidenceRefs` 존재 검증
- [ ] 교차 Repository 참조 금지
- [ ] P0/P1/P2 타입·깊이 조합 검증
- [ ] `completedEvidenceLevels`와 실제 Evidence 일치
- [ ] P2 snippet 필수 메타데이터 검증
- [ ] 참조 순환과 상향 깊이 파생 방지

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

- [ ] Repository별 독립 생성
- [ ] Evidence·Claim 참조 검증 연결
- [ ] 입력에 없는 기술·파일 검출
- [ ] P1 기여율·실력 단정 검출
- [ ] P2 Repository 전체 일반화 검출
- [ ] `NOT_OBSERVED` 오용 검출
- [ ] 최초 정책 실패 시 최대 1회 재생성
- [ ] 재검증 실패 시 전체 분석 오류

### Phase 7. Portfolio·Interview·Statement 생성

대상:

```text
ai/app/services/portfolio_service.py
ai/app/prompts/portfolio.py
ai/app/prompts/interview.py
ai/tests/test_portfolio_service.py
```

구현:

- [ ] 전체 요약
- [ ] 대표 Repository
- [ ] 단일 `jobAppeal`
- [ ] Evidence 기반 strengths/gaps/nextActions
- [ ] 면접 질문과 답변 방향
- [ ] 포트폴리오 문장
- [ ] 전체 범위 참조 검증

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
입력 검증
→ Repository 정규화
→ Criteria/Prompt
→ Repository 분석
→ Portfolio 종합
→ 최종 정책 검증
→ InternalPortfolioReport
```

구현:

- [ ] `LLMProvider` 의존성 주입
- [ ] Repository 1~5개 처리
- [ ] 혼합 깊이 처리
- [ ] Repository 하나 실패 시 전체 실패
- [ ] 모든 Gemini 호출·retry를 포함한 270초 전체 deadline
- [ ] 단계별 처리 시간과 시도 횟수 집계

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
