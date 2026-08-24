# GitDdo 평가 계약 기준

## 1. 목적과 기준 시점

이 문서는 GitDdo 평가 시스템의 근거 철학, P0/P1/P2 의미, 책임 경계와 Wire 계약의 주요
의미를 설명한다. JSON 필드를 복제하는 문서가 아니며, 실제 request·response·error 필드의
최종 Source of Truth는 Backend JSON Schema이다.

```text
backend/backend/docs/contracts/analysis-request.schema.json
backend/backend/docs/contracts/analysis-response.schema.json
backend/backend/docs/contracts/analysis-error.schema.json
```

Markdown과 Schema가 충돌하면 Backend Schema, Java DTO, Assembler, Validator 순서로 확인한다.

이 문서의 Backend 기준선은 다음과 같다.

```text
Backend main: 21a8c30 (P1 병합)
Backend P2 branch: origin/feat/portfolio-evaluation-p2
Backend P2 commit: bcc9a4f
```

P2 관련 내용은 아직 병합되지 않은 위 작업 브랜치를 읽기 전용으로 확인해 동기화했다. P2가
`main`에 병합되면 Schema와 구현을 다시 점검한다.

## 2. 서비스 정의

GitDdo는 GitHub 기반 실력 자동 채점 서비스가 아니다. 공개적으로 확인되는 근거와 사용자
진술을 분리해 다음 자료를 제공하는 포트폴리오 코칭 서비스이다.

- Repository별 관찰 결과
- 전체 포트폴리오의 직무 어필 포인트
- 근거 기반 개선 방향
- 포트폴리오 문장 초안
- 프로젝트 기반 면접 질문과 답변 방향
- 분석 범위와 한계

평가 결과는 사용자의 실력, 기여율, 경력 수준 충족 여부 또는 합격 가능성을 단정하지 않는다.

## 3. 책임 경계

### 3.1 Spring Boot

- GitHub OAuth와 사용자·포트폴리오 소유권 관리
- 평가용 Repository 1~5개 검증
- default branch와 Snapshot SHA 고정
- P0/P1/P2 Evidence 수집·선별
- Evidence와 UserClaim ID 발급
- Evaluation Job 상태 관리
- AI request 조립과 저장
- AI response의 Schema·Snapshot·참조 최종 검증
- 검증된 결과 저장 또는 Job 실패 처리

### 3.2 FastAPI AI 서버

- `POST /internal/v1/portfolio-reports` 요청 검증
- 전달된 Evidence와 UserClaim만 해석
- Repository별 완료 깊이에 맞는 코칭 결과 생성
- Evidence·Claim 참조, 분석 깊이와 내용 정책 검증
- 성공 response 또는 공통 Error Envelope 반환

### 3.3 AI 서버 금지 사항

- GitHub API 직접 호출
- 저장소 전체 코드 또는 GitHub raw response 요청
- 전달된 코드 실행
- Job, 결과, 멱등성 상태 저장
- DB, Redis 또는 in-memory Job Lock 사용
- 커밋 수·변경량을 실력이나 기여율로 변환

## 4. 핵심 개념

```text
Evidence
Backend가 GitHub에서 확인하거나 규칙으로 도출한 사실

UserClaim
사용자가 직접 입력한 역할·참여 수준·구현 경험에 관한 진술

Finding / Coaching Item
AI가 Evidence와 UserClaim을 해석해 생성한 결과
```

UserClaim은 Evidence가 아니다. AI 추천도 Evidence가 아니다. 사용자 진술과 공개 근거가
충돌하거나 근거가 부족하면 확정적으로 단정하지 않는다.

`NOT_OBSERVED`는 수집 범위에서 확인하지 못했다는 뜻이다. 실제 부재, 거짓 또는 미기여로
해석하지 않는다. 누락을 근거로 추천하려면 Backend가 명시적인 `BACKEND_DERIVED` Evidence를
전달해야 한다.

## 5. Wire 계약 확정값

Backend Schema·DTO·Assembler가 일치하는 현재 계약은 다음과 같다.

| 항목 | 현재 계약 |
| --- | --- |
| 계약 버전 필드 | `schemaVersion` |
| 계약 버전 값 | `"1.0"` |
| `analysisId` | UUID 문자열 |
| `repositoryId` | GitHub Repository numeric ID의 문자열 표현 |
| Finding ID | `findingId`, `^find_[0-9]{3,}$` |
| Evidence ID | `evidenceId`, `^ev_[0-9]{3,}$` |
| Claim ID | `claimId`, `^claim_[0-9]{3,}$` |
| 분석 목적 | `PORTFOLIO_ANALYSIS` |
| 분석 깊이 | `P0`, `P1`, `P2` |

Snapshot 내부 구조 버전은 Backend의 정수 `schemaVersion`을 별도로 사용한다. Wire
`schemaVersion="1.0"`, Snapshot 구조 버전, `extractorVersion`, AI `evaluatorVersion`을 서로
혼동하지 않는다.

현재 Backend는 `findingId`를 하나의 응답 전체에서 유일하게 검증한다. Evidence와 Claim ID도
Assembler가 분석 전체 범위에서 연속 발급하지만, Schema만으로는 전역 유일성을 표현할 수
없으므로 양쪽 의미 Validator가 별도로 검사해야 한다.

## 6. P0 / P1 / P2

### 6.1 P0: 정적 Repository 근거

대표 근거:

```text
Repository metadata
README
file tree
languages
build/dependency manifest
test structure
Docker/Compose configuration
GitHub Actions
API documentation
BACKEND_DERIVED static fact
```

허용 판단:

- README와 공개 문서의 준비 상태
- 의존성·설정 파일에서 관찰되는 기술
- 테스트·Docker·Actions 구성의 관찰 여부
- 공개 근거만으로 포트폴리오에서 설명 가능한 범위

금지 판단:

- 코드·설계·테스트·보안 품질
- 사용자 기술 숙련도와 기여율
- 취업 가능성 또는 경력 수준 충족 여부

### 6.2 P1: GitHub 활동 근거

대표 근거:

```text
commit SHA와 요약
PR number와 PR 요약
changed paths
활동 기간과 최근 활동
Backend가 선별한 activity summary
```

허용 판단:

- 특정 경로·커밋·PR에서 활동이 관찰되었다는 사실
- UserClaim과 연결 가능한 활동 근거의 존재
- 변경 경로 기반 활동 영역 후보

금지 판단:

- 커밋 수 또는 변경 라인 수를 실력으로 해석
- 커밋 비율을 개인 기여율로 변환
- 활동이 보이지 않는 것을 미기여·거짓으로 판정
- P1만으로 코드 품질을 판단

Backend `main`의 P1 Collector는 최근 커밋 창과 PR에서 노이즈를 제외하고 변경 임팩트 기반으로
근거를 선별한다. 이 점수는 Evidence 선택용이지 사용자 평가 점수가 아니다.

### 6.3 P2: 제한된 코드 근거

P2는 Repository 전체 코드를 분석하지 않는다. Backend가 P1의 변경 파일·PR에서 후보를 골라
짧은 코드 또는 테스트 snippet을 `CODE_EVIDENCE`로 전달한다.

현재 Wire Schema에 존재하는 P2 관련 Evidence 필드는 다음과 같다.

```text
evidenceType = CODE_EVIDENCE
analysisDepth = P2
factKey = CODE_SNIPPET
value = snippet 문자열
path
startLine
endLine
commitSha
pullRequestNumber
sourceEvidenceRefs
```

Backend 내부 Snapshot에는 `contentHash`와 `truncated`가 있지만 현재 AI request Schema에는 없다.
`language`도 현재 Wire 필드가 아니다. Schema가 바뀌기 전 해당 값을 AI request 필수 필드로
가정하지 않는다.

허용 판단:

- 제공된 코드 구간에서 관찰되는 입력 검증과 오류 처리
- 제공된 코드 구간의 책임과 호출 관계
- 제공된 테스트 구간에서 관찰되는 테스트 사례
- 코드 구간을 포트폴리오·면접에서 설명할 수 있는 방법

금지 판단:

- Repository 전체 코드 품질로 일반화
- 프로젝트 전체 아키텍처가 우수하다고 단정
- 일부 코드만으로 사용자 숙련도·기여율·경력 수준을 판정
- 입력에 없는 코드, 파일, 기술 또는 구현 사실 생성

## 7. 요청 깊이와 Repository별 완료 깊이

`requestedAnalysisDepth`는 요청 전체가 목표로 하는 최대 깊이이다.
`completedEvidenceLevels`는 각 Repository에서 실제 수집된 깊이이다.

```text
requestedAnalysisDepth: P2

Repo A completedEvidenceLevels: [P0, P1, P2]
Repo B completedEvidenceLevels: [P0, P1]
Repo C completedEvidenceLevels: [P0]
```

AI는 Repository별 `completedEvidenceLevels`까지만 판단한다. Repo A의 P2 Evidence를 Repo B나
Repo C의 코드 품질 판단에 재사용하지 않는다. `usedEvidenceLevels`에는 실제 응답이 사용한
깊이만 넣고, 요청보다 깊거나 수집되지 않은 수준을 포함하지 않는다.

## 8. Evidence와 UserClaim 계약

Evidence 타입은 다음과 같다.

| EvidenceType | 기본 깊이 | 의미 |
| --- | --- | --- |
| `GITHUB_STATIC` | P0 | README·트리·설정 등 GitHub에서 확인된 정적 사실 |
| `GITHUB_ACTIVITY` | P1 | 커밋·PR·변경 경로 등 관찰된 활동 |
| `CODE_EVIDENCE` | P2 | Backend가 선별한 코드·테스트 snippet |
| `BACKEND_DERIVED` | P0+ | Backend가 명시적 규칙으로 도출한 사실 |

현재 request의 UserClaim 필드는 다음과 같다.

```text
claimId
statement
participationLevel
participationStartedOn
participationEndedOn
relatedEvidenceRefs
```

Claim의 `relatedEvidenceRefs`는 주장과 공개 근거의 연결 후보이다. 연결되었다고 해서 Claim이
검증된 사실로 승격되지는 않는다.

입력 참조 기본 규칙:

- Evidence·Claim ID는 분석 전체에서 유일해야 한다.
- Evidence와 Claim은 자신의 `repositoryId`·`repositoryFullName`과 일치해야 한다.
- `sourceEvidenceRefs`와 Claim의 `relatedEvidenceRefs`는 존재하는 Evidence를 참조해야 한다.
- 참조 대상은 같은 Repository와 같은 Snapshot 범위여야 한다.
- P2 `CODE_EVIDENCE`는 자신을 선택하게 한 P1 Evidence와 연결해야 한다.

Backend Assembler는 ID를 전역 순번으로 생성하지만, 입력 참조의 전역 유일성·Repository 범위와
`sourceEvidenceRefs` 무결성은 Backend Validator에서 아직 전부 강제하지 않는다.

## 9. 현재 Response 계약

현재 응답 최상위 필드는 다음과 같다.

```text
schemaVersion
analysisId
evaluatorVersion
requestedAnalysisDepth
usedEvidenceLevels
summary
repositories
coaching
limitations
```

### 9.1 Repository Finding

```text
repositoryId
repositoryFullName
snapshotHashAlgorithm
snapshotSha
findings[]
  findingId
  category
  severity
  title
  detail
  evidenceRefs
  claimRefs
```

Backend Validator는 Finding이 같은 Repository의 Evidence·Claim만 참조하도록 검증한다.
`ACTIVITY`는 P1 Evidence, `CODE_QUALITY`는 P2 Evidence를 반드시 인용한다.

현재 Schema와 Validator는 모든 P0 Finding에 `evidenceRefs >= 1`을 강제하지 않는다. 사실 기반
Finding은 Evidence를 최소 하나 가져야 한다는 최종 정책을 적용하려면 Backend 보완이 필요하다.

### 9.2 Coaching

| 필드 | 현재 구조와 참조 규칙 |
| --- | --- |
| `strengths` | 배열, 각 항목 Evidence 최소 1개 |
| `gaps` | 배열, 각 항목 Evidence 최소 1개 |
| `nextActions` | 배열, 각 항목 Evidence 최소 1개 |
| `jobAppeal` | 전체 포트폴리오 기준 단일 객체, Evidence 최소 1개 |
| `portfolioStatements` | 배열, Evidence 또는 Claim 최소 1개 |
| `interviewQuestions` | 배열, Evidence 또는 Claim 최소 1개 |

`jobAppeal`, `strengths`, `gaps`, `nextActions`는 전체 Portfolio 범위 Evidence를 참조할 수 있다.

현재 `portfolioStatements`에는 `text`, `evidenceRefs`, `claimRefs`만 있다. 다음 필드는 과거
합의가 있었지만 Backend Schema에 아직 반영되지 않았다.

```text
repositoryId
type: RESUME | PORTFOLIO | INTERVIEW
```

현재 `interviewQuestions`에는 다음 필드만 있다.

```text
question
intent
answerGuide
evidenceRefs
claimRefs
```

`repositoryId`와 `followUpQuestions`는 현재 계약에 없다. 문장·질문에 Repository 범위를
강제하려면 `repositoryId`를 Backend Schema·DTO·Validator에 먼저 추가해야 한다.

## 10. Limitations와 Collection Warnings

Backend request는 Repository별 `collectionWarnings`를 전달한다. P0/P1/P2 Collector가 입력
축소, 파일 조회 실패, Secret·바이너리 제외 등의 Warning을 생성한다.

현재 response `LimitationCode`는 다음 세 개뿐이다.

```text
P0_ONLY
MISSING_ACTIVITY_EVIDENCE
MISSING_CODE_EVIDENCE
```

현재 `collectionWarnings`를 `limitations`로 변환하는 명시적 계약은 없다.
`PARTIAL_COLLECTION` 또는 동등한 Limitation Code를 추가하고 Warning을 사용자에게 어떻게
요약할지 Backend와 AI가 추가 합의해야 한다.

## 11. Error Envelope와 HTTP Status

현재 Error Envelope는 다음 필드를 사용한다.

```text
schemaVersion
analysisId
code
message
retryable
details (object)
```

현재 Error Code:

```text
INVALID_REQUEST
UNSUPPORTED_COMBINATION
POLICY_VIOLATION
LLM_TIMEOUT
LLM_RATE_LIMITED
LLM_SERVICE_ERROR
STRUCTURED_OUTPUT_INVALID
INTERNAL_ERROR
```

AI API의 HTTP status 계약은 다음으로 확정한다. AI 서버 구현은 아직 필요하다.

| Code | HTTP | retryable |
| --- | ---: | --- |
| `INVALID_REQUEST` | 400 | false |
| `UNSUPPORTED_COMBINATION` | 422 | false |
| `POLICY_VIOLATION` | 502 | false |
| `LLM_TIMEOUT` | 504 | true |
| `LLM_RATE_LIMITED` | 503 | true |
| `LLM_SERVICE_ERROR` | 502 | true |
| `STRUCTURED_OUTPUT_INVALID` | 502 | false |
| `INTERNAL_ERROR` | 500 | false |

Backend HTTP Client는 non-2xx 응답의 Error Envelope를 파싱해 `code`와 `retryable`을 실패
사유에 보존한다. 현재 Backend는 Error Code별로 재시도하지 않는다.

## 12. Retry와 Timeout

MVP retry 정책:

```text
Gemini Provider
→ 429, timeout, 5xx에 한해 제한적 retry

AI 서버 최종 실패
→ Error Envelope 반환

Spring Boot
→ 자동 재호출하지 않음
→ Evaluation Job FAILED
```

`retryable`은 향후 수동 재분석 또는 자동 retry 기능을 위한 메타데이터이다.

임시 운영 timeout 계약:

```text
Backend → AI Connect Timeout: 5초
AI 서버 전체 처리 Deadline: 270초
Backend → AI Read Timeout: 300초
```

Gemini 개별 호출 timeout은 전체 270초 deadline과 다르다. retry와 backoff도 270초 안에
포함되어야 한다. Backend `AiClientConfig`에는 현재 connect/read timeout이 적용되지 않았고,
AI에도 전체 deadline이 구현되지 않았으므로 양쪽 모두 구현 예정이다.

## 13. 부분 성공 정책

MVP는 Repository별 부분 성공을 지원하지 않는다.

```text
Repository 하나의 분석 또는 필수 검증 실패
→ 전체 AI 분석 실패
→ Error Envelope
→ Backend Job FAILED
```

Backend Validator도 request와 response의 Repository 수·ID가 정확히 일치해야 성공하도록
검증한다. 향후 부분 성공이 필요하면 Repository별 status/error를 별도 계약으로 추가한다.

## 14. P2 수집 예산 현황

Backend P2 브랜치에서 실제로 적용되는 제한은 다음과 같다.

| 항목 | 현재 P2 구현 |
| --- | ---: |
| Repository별 snippet | 최대 8개 |
| Repository별 후보 파일 | 최대 16개 |
| 원본 파일 크기 | 최대 80,000 byte |
| snippet 라인 | 최대 40줄 |
| snippet 문자 | 최대 4,000자 |
| P2 대상 Repository | 선택된 모든 Repository 순회 |
| 전체 snippet | 전역 제한 없음 |
| 전체 Evidence/token | 전역 제한 없음 |

과거 문서의 `최대 3개 Repository`, `전체 24개 snippet`, `Repository별 10개`, `120줄`,
`30,000 tokens`는 현재 Backend 구현값이 아니므로 최종 계약에서 제거한다.

전역 제한이 없으면 Repository 5개에서 최대 40개 snippet이 생성될 수 있다. Backend는 P2
대상 Repository 수, 전체 snippet 및 전체 token 예산을 추가로 합의하고 구현해야 한다.

현재 후보 선택은 P1 `CHANGED_FILES`와 `PULL_REQUEST`를 기반으로 변경 임팩트를 계산한다.
사용자가 직접 지정한 파일, 역할과 연결된 경로, Production/Test 쌍을 우선하는 정책은 아직
구현되어 있지 않다.

## 15. P2 보안과 보관 현황

P2 브랜치는 다음 파일·내용을 제외한다.

- `.env`, `.env.*`, `*.pem`, `*.key`
- 경로에 `credentials` 또는 `/secrets/`가 포함된 파일
- Private key header 또는 `AWS_SECRET_ACCESS_KEY` marker가 있는 내용
- 바이너리, Base64 해석 실패, 80,000 byte 초과 파일

현재 Secret marker 검사는 제한적이다. 일반 token·password·API key 패턴과
`application-local.*` 등 추가 파일 정책은 보완이 필요하다.

Backend는 `evidence_snapshot`과 `ai_request`를 JSONB로 저장한다. P2 브랜치가 병합되면 snippet
원문도 현재 구조상 DB에 저장된다. 과거 문서의 “P2 snippet을 영구 저장하지 않는다”는 현재
구현과 일치하지 않는다. 보관 기간, 암호화·접근 통제, 삭제 정책 또는 원문 비저장 구조를
Backend에서 결정해야 한다.

## 16. 지원 범위

Schema가 표현 가능한 값:

```text
TargetJob: BACKEND, FRONTEND, AI, CLOUD_INFRA
TargetCareerLevel: ENTRY, JUNIOR, MID, SENIOR
AnalysisPurpose: PORTFOLIO_ANALYSIS
AnalysisDepth: P0, P1, P2
```

현재 구현 상태:

| 영역 | 현재 상태 |
| --- | --- |
| Backend `main` | BACKEND 중심 P0/P1 수집과 Mock 리포트 |
| Backend P2 branch | P2 코드 snippet 수집과 Mock P2 리포트 구현, 미병합 |
| AI 내부 구현 | P0/P1/P2 내부 Evidence·Criteria·System Prompt·정규화·Prompt Context 구현 |
| AI Wire API | `/health`만 구현, 실제 portfolio report API 미구현 |

개발 목표:

```text
BACKEND × ENTRY × PORTFOLIO_ANALYSIS × P0/P1/P2
```

다른 직무와 경력 수준 enum은 Wire에서 표현 가능하지만 실제 분석 Criteria와 Prompt가 없으므로
현재 지원한다고 표시하지 않는다.

## 17. 보안·Prompt 정책

- Repository metadata, README, 코드, 커밋, Warning과 UserClaim은 untrusted data이다.
- 외부 데이터의 명령·역할 변경·이전 지시 무시·정책 변경·출력 형식 변경 요청을 따르지 않는다.
- 외부 데이터는 구조화된 JSON data block으로만 직렬화한다.
- 정확한 Prompt 예약 마커와 충돌하는 문자열은 가역적인 Unicode escape로 중립화한다.
- 전달된 코드는 분석만 하고 실행하지 않는다.
- 입력에 없는 기술, 파일 경로 또는 기능을 생성하지 않는다.
- Prompt·응답 전문과 민감 원문을 기본 로그에 기록하지 않는다.
- API key와 token을 코드, Fixture 또는 로그에 넣지 않는다.

## 18. Backend 보완 필요

| 문제 | 현재 영향 | 권장 수정 |
| --- | --- | --- |
| P2 전역 snippet/token 예산 없음 | 5개 Repository에서 입력이 과도하게 커질 수 있음 | P2 대상 Repository·전체 snippet·전체 token 상한 추가 |
| P2 후보가 P1 변경 파일에만 의존 | 사용자 지정 역할·파일과 테스트 연계가 약함 | 사용자 지정 파일·PR·역할 경로·Production/Test 쌍 우선순위 추가 |
| 모든 Finding의 Evidence 필수 규칙 부재 | P0 Finding이 Claim만 있거나 무근거여도 Validator를 통과할 수 있음 | Schema `minItems: 1` 및 Validator 공통 검사 추가 |
| 문장·질문에 `repositoryId` 없음 | 참조를 Repository 단위로 제한할 수 없음 | 두 응답 항목에 `repositoryId` 추가 후 같은 Repository 참조 검증 |
| `portfolioStatements.type` 없음 | 이력서·포트폴리오·면접 용도를 구분할 수 없음 | `RESUME`, `PORTFOLIO`, `INTERVIEW` enum 추가 |
| Warning→Limitation 계약 없음 | 수집 축소·실패가 결과에 일관되게 노출되지 않음 | `PARTIAL_COLLECTION` 등 Limitation과 매핑 정책 추가 |
| Backend AI HTTP timeout 미적용 | 합의한 5초/300초가 실제로 보장되지 않음 | RestClient request factory에 connect/read timeout 적용 |
| 입력 참조 Validator 부족 | 중복 ID·교차 Repository `sourceEvidenceRefs`가 계약상 통과 가능 | 요청 의미 Validator에 전역 유일성·소유 관계·깊이 검사 추가 |
| P2 snippet 저장 정책 미확정 | 코드 원문이 JSONB에 장기 보관될 수 있음 | 보관 기간·접근 통제·삭제 또는 비저장 정책 확정 |
| Secret 탐지 범위가 좁음 | 일부 credential 원문이 snippet에 포함될 수 있음 | 제외 파일과 token/password/API key 탐지 규칙 보완 |
| Snapshot SHA 형식 검증 부재 | 알고리즘과 실제 SHA 길이가 불일치해도 Schema를 통과할 수 있음 | SHA1 40자·SHA256 64자 hex 조건을 Schema/Validator에 추가 |

`followUpQuestions`는 현재 MVP 필수 계약이 아니므로 Backend 수정 필요 항목으로 보지 않는다.
필요해질 때 별도 확장한다.

## 19. AI 구현 순서

Backend P2 흐름에 맞추는 AI 구현 순서는 다음과 같다. 1~2단계는 완료했다.

1. P1/P2 내부 Evidence 도메인 모델 확장 (완료)
2. P1/P2 Criteria와 Loader 확장 (완료)
3. 혼합 깊이 System Prompt 구현 (완료)
4. P1/P2 정규화와 Prompt Context 구현 (완료)
5. 입력 참조·깊이 Validator 구현
6. Repository Service와 결과 정책 Validator 구현
7. Portfolio·Interview·Statement 생성과 Report Service 구현
8. Backend Schema 기준 Pydantic Wire DTO와 Error Envelope 구현
9. `POST /internal/v1/portfolio-reports` 구현
10. Fake Provider 기반 P0/P1/P2 계약 테스트
11. 실제 Gemini와 Spring Boot E2E 연동

각 작업은 별도 논리적 커밋으로 구현하고, 구현되지 않은 기능을 문서에서 완료 상태로 표시하지
않는다.
