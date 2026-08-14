# Gitddo 평가 계약 및 AI 서버 설계 변경 가이드

## 1. 문서 목적

이 문서는 AI 코딩 에이전트가 백엔드와 합의한 평가 계약을 기준으로 다음 작업을 순서대로 수행하기 위한 실행 가이드이다.

- 기존 문서의 오래된 평가 설계 수정
- 백엔드와 AI 서버가 공유하는 계약 작성
- Pydantic 요청·응답 모델 재설계
- JSON Schema와 공용 Fixture 생성
- Evidence 및 분석 깊이 검증 구현
- Mock 내부 API 구현
- 보안과 입력 제한 적용

모든 작업은 한 번에 구현하지 않는다. 백엔드와 AI가 Fake·Stub으로 각자의 핵심 기능을 먼저 완성하고, 최종 DTO·Schema·Fixture와 실제 HTTP 연동은 뒤에서 확정한다. 실행 순서는 이 문서의 변경된 Phase와 `docs/guide.md`를 따른다.

---

## 2. 서비스 정의

Gitddo는 GitHub 기반 실력 자동 채점 서비스가 아니다.

GitHub에서 공개적으로 확인되는 근거와 사용자 진술을 분리하고, 이를 바탕으로 포트폴리오 어필 포인트·보완 방향·면접 준비 자료를 제공하는 코칭 서비스이다.

평가 결과에서 다음 세 범주를 반드시 구분한다.

```text
Evidence
백엔드가 GitHub에서 확인하거나 규칙으로 도출한 정보

UserClaim
사용자가 직접 입력한 역할과 경험

ReportItem
AI가 생성한 관찰·해석·추천·면접 질문
```

---

## 3. 작업 전 필수 규칙

AI 에이전트는 작업 전 다음 문서를 읽는다.

```text
AGENTS.md
README.md
ai/README.md
docs/guide.md
docs/github-workflow.md
```

작업 시작 전 다음을 확인한다.

```bash
git status --short --branch
```

작업 원칙은 다음과 같다.

- 사용자의 기존 변경을 되돌리거나 덮어쓰지 않는다.
- Phase 1의 FastAPI, `/health`, 설정, Docker, 검사 환경은 유지한다.
- 기존 Phase 2 커밋을 reset 또는 revert하지 않는다.
- 설계 변경은 새로운 커밋으로 기록한다.
- 하나의 논리적 작업 단위마다 검증 후 로컬 `main`에 커밋한다.
- 검증에 실패한 상태에서는 완료 커밋을 만들지 않는다.
- 사용자가 요청하지 않으면 push, merge, rebase, PR 생성은 하지 않는다.
- 문서·계약·코드가 충돌하면 임의로 결정하지 말고 사용자에게 보고한다.

---

## 4. 확정된 MVP 범위

```text
평가 저장소: 1~5개
지원 직무: BACKEND
목표 경력: ENTRY
분석 목적: PORTFOLIO_ANALYSIS
지원 분석 깊이: P0
계약 버전: 1.0
```

Schema에는 확장 예정 enum을 포함할 수 있지만, 현재 지원하지 않는 조합은 `UNSUPPORTED_COMBINATION` 오류로 거절한다.

향후 확장 단계는 다음과 같다.

```text
MVP 1
BACKEND × ENTRY × PORTFOLIO_ANALYSIS × P0

MVP 2
P1 커밋·PR 활동 근거와 사용자 진술 연결

MVP 3
P2 코드 근거와 기술 코칭
```

P2 제한은 다음과 같다.

```text
대상 저장소: 최대 3개
전체 snippet: 최대 24개
저장소별 snippet: 최대 10개
snippet당 최대 120줄
전체 evidence 입력: 최대 30,000 tokens
```

---

## 5. 책임 경계

### 5.1 Spring Boot 책임

- GitHub OAuth와 사용자 관리
- 포트폴리오 소유권 검증
- GitHub API 호출
- 저장소 존재 및 접근 권한 검증
- default branch와 Snapshot SHA 고정
- P0/P1/P2 데이터 수집
- Evidence ID 발급
- Secret, 바이너리, 생성 파일, 대용량 파일 제거
- 사용자 진술 저장
- Evaluation Job과 상태 관리
- AI 요청 전 JSON Schema 검증
- AI 응답 최종 검증
- 검증된 리포트 DB 저장

### 5.2 AI 서버 책임

- GitHub API를 직접 호출하지 않음
- 저장소 전체 코드와 GitHub raw response를 받지 않음
- 전달된 Evidence와 UserClaim만 해석
- 합의된 직무·분석 목적에 맞는 코칭 리포트 생성
- Pydantic 요청·응답 검증
- Evidence 참조와 분석 깊이 검증
- 모든 Recommendation의 Evidence 참조 검증
- `jobAppeal`과 `portfolioStatements`의 참조 규칙 검증
- README·코드·사용자 입력을 신뢰할 수 없는 데이터로 처리
- 외부 입력에 포함된 지시문을 따르지 않음
- 전달된 코드를 실행하지 않음
- 분석 결과를 직접 DB에 저장하지 않음
- Job, 결과, 멱등성 정보를 저장하지 않음
- DB, Redis, in-memory Job Lock을 사용하지 않는 stateless 서버로 유지

---

## 6. API 흐름

### 6.1 Frontend → Spring Boot

```http
POST /api/v1/portfolios/{portfolioId}/evaluations
Idempotency-Key: <client-generated-key>
```

- 비동기 Evaluation Job을 생성한다.
- 포트폴리오 소유권을 검증한다.
- 정상 생성 시 `202 Accepted`를 반환한다.

```json
{
  "analysisId": "86f02adc-9f55-46c7-a498-dc8dca88ef69",
  "status": "REQUESTED"
}
```

```http
GET /api/v1/portfolios/{portfolioId}/evaluations/{analysisId}
```

- 진행 상태를 반환한다.
- 완료되면 저장된 리포트를 반환한다.

Job 상태는 다음을 사용한다.

```text
REQUESTED
COLLECTING
ANALYZING
SUCCEEDED
FAILED
```

### 6.2 Spring Boot → AI 서버

```http
POST /internal/v1/portfolio-reports
Content-Type: application/json
```

- 동기 HTTP API로 처리한다.
- AI 서버는 성공 시 `200 OK`를 반환한다.
- 비동기 Job과 상태 관리는 Spring Boot가 담당한다.

---

## 7. 버전과 식별자

버전의 책임을 다음과 같이 분리한다.

```text
contractVersion: "1.0"
백엔드와 AI 서버 사이의 요청·응답 계약 버전

snapshotSchemaVersion: 1
백엔드가 생성한 저장소 Snapshot 구조 버전

snapshotHashAlgorithm: "SHA1" 또는 "SHA256"
snapshotSha 해석과 길이 검증에 사용하는 Git 객체 해시 알고리즘

extractorVersion: "p0-collector-1.0"
백엔드 Evidence 수집기 버전

promptVersion: "backend-entry-p0-1.0"
AI Prompt 버전
```

`schemaVersion`이라는 공통 이름을 여러 의미로 사용하지 않는다.

식별자는 다음 규칙을 따른다.

```text
DB PK: Long 사용 가능
외부 analysisId: UUID v4
repositoryId: GitHub Repository numeric ID
evidenceId: ev_001 형식
claimId: claim_001 형식
itemId: item_001 형식
contentHash: SHA-256 lowercase hex
```

`snapshotSha`는 Repository에 함께 전달된 `snapshotHashAlgorithm`을 기준으로 검증한다. SHA-1은 40자리, SHA-256은 64자리 hex 문자열을 사용한다. 대소문자와 Git object format 세부 규칙은 공용 JSON Schema 확정 시 백엔드와 최종 확인한다.

ID 문자열 패턴은 다음을 기준으로 한다.

```text
evidenceId: ^ev_[0-9]{3,}$
claimId: ^claim_[0-9]{3,}$
itemId: ^item_[0-9]{3,}$
```

`evidenceId`, `claimId`, `itemId`는 각각 하나의 `analysisId` 전체에서 유일해야 한다. Repository가 달라져도 번호를 다시 시작하지 않는다.

```text
repo1: ev_001, ev_002
repo2: ev_003, ev_004
```

Evidence 참조는 토큰 절약을 위해 문자열 ID 배열을 사용한다.

```json
{
  "evidenceRefs": ["ev_001", "ev_002"]
}
```

백엔드는 `analysisId + evidenceId`로 Evidence를 찾고 내부의 `repositoryFullName`, `snapshotSha`, `contentHash`를 검증한다.

---

## 8. 공통 계약 규칙

```text
contractVersion: "1.0"
JSON Schema: Draft 2020-12
JSON 필드명: camelCase
enum: UPPER_SNAKE_CASE
날짜: ISO 8601 full-date (`YYYY-MM-DD`)
날짜·시간: ISO 8601 UTC
빈 목록: []
선택 값 없음: null
알 수 없는 필드: 거절
```

버전 변경 정책은 다음과 같다.

```text
하위 호환 필드 추가: minor 증가
필드 삭제·타입 변경·의미 변경: major 증가
```

---

## 9. 공통 Enum

### 9.1 현재 및 확장 예정 값

```text
TargetJob
- BACKEND
- FRONTEND
- AI
- CLOUD_INFRA

TargetCareerLevel
- ENTRY
- MID
- SENIOR

AnalysisPurpose
- PORTFOLIO_ANALYSIS

AnalysisDepth
- P0
- P1
- P2

ProjectType
- PERSONAL
- TEAM

ParticipationLevel
- PRIMARY
- CONTRIBUTOR
- SUPPORT

EvidenceType
- GITHUB_STATIC
- GITHUB_ACTIVITY
- CODE_EVIDENCE
- BACKEND_DERIVED

ReportItemType
- OBSERVATION
- INTERPRETATION
- RECOMMENDATION
- INTERVIEW_QUESTION

StatementSupportStatus
- SUPPORTED
- PARTIALLY_SUPPORTED
- NOT_OBSERVED
- CONFLICTING

Confidence
- HIGH
- MEDIUM
- LOW
- NOT_VERIFIABLE

Priority
- HIGH
- MEDIUM
- LOW

StatementType
- RESUME
- PORTFOLIO
- INTERVIEW

SnapshotHashAlgorithm
- SHA1
- SHA256

EvidenceValueType
- STRING
- BOOLEAN
- INTEGER
- DECIMAL
- STRING_LIST
```

### 9.2 MVP 런타임 허용 조합

```text
targetJob: BACKEND
targetCareerLevel: ENTRY
analysisPurpose: PORTFOLIO_ANALYSIS
requestedAnalysisDepth: P0
```

확장 예정 enum이 요청에 들어오면 형식 검증 이후 서비스 계층에서 `UNSUPPORTED_COMBINATION`으로 거절한다.

---

## 10. Evidence, UserClaim, ReportItem 계약

### 10.1 Evidence

GitHub와 백엔드에서 확인하거나 도출한 정보만 Evidence로 취급한다.

| 유형 | 의미 | 생성 주체 | 깊이 |
|---|---|---|---|
| `GITHUB_STATIC` | README·트리·설정·언어 | 백엔드 | P0 |
| `GITHUB_ACTIVITY` | 커밋·PR·변경 경로 | 백엔드 | P1 |
| `CODE_EVIDENCE` | 허용된 코드·테스트 구간 | 백엔드 | P2 |
| `BACKEND_DERIVED` | 규칙 기반 도출 정보 | 백엔드 | P0+ |

Evidence 공통 필드:

```text
evidenceId
evidenceType
analysisDepth
repositoryFullName
snapshotSha
contentHash
summary
```

선택적 위치 정보:

```text
path
startLine
endLine
commitSha
pullRequestNumber
```

`BACKEND_DERIVED` 추가 필드:

```text
sourceEvidenceRefs
derivedFromLevel
```

Evidence는 `evidenceType`을 discriminator로 사용하는 모델로 구현한다. 유형별 최소 데이터는 다음과 같다.

```text
GitHubStaticEvidence
- factKey
- valueType
- value
- path(optional)

GitHubActivityEvidence
- activityKind
- observedAt
- commitSha 또는 pullRequestNumber
- changedPaths

CodeEvidence
- path
- startLine
- endLine
- language
- snippet

BackendDerivedEvidence
- metricKey
- valueType
- value
- sourceEvidenceRefs
- derivedFromLevel
```

Evidence `value`는 `EvidenceValueType`에 따라 다음 값만 허용한다.

```text
STRING      → JSON string
BOOLEAN     → JSON boolean
INTEGER     → JSON integer
DECIMAL     → JSON decimal 표현
STRING_LIST → JSON string array
```

자유 형식 object, 중첩 object, 임의 배열은 허용하지 않는다. `DECIMAL`의 JSON number 또는 string 표현, `valueType` 필드의 최종 명칭과 각 값의 길이·범위는 공용 JSON Schema 작성 전에 백엔드와 확정한다.

`contentHash`는 다음 규칙으로 생성한다.

```text
README·설정·코드처럼 텍스트가 전달되는 Evidence
→ Secret 제거와 정규화를 마친 실제 전달 텍스트의 SHA-256

Activity·Derived처럼 구조화된 값만 전달되는 Evidence
→ key 정렬과 공백 제거를 적용한 canonical JSON UTF-8 바이트의 SHA-256
```

### 10.2 UserClaim

사용자가 입력한 역할·구현 내용은 Evidence와 분리한다.

```text
claimId
statement
participationLevel
participationStartedAt
participationEndedAt
relatedEvidenceRefs
```

`participationStartedAt`과 `participationEndedAt`은 ISO 8601 full-date(`YYYY-MM-DD`) 또는 `null`을 사용한다. 시작일·종료일의 필수 여부와 기간 역전 검증 규칙은 공용 계약에서 확정한다.

### 10.3 UserClaim 연결 상태

```text
SUPPORTED
사용자 진술과 직접 연결되는 근거가 확인됨

PARTIALLY_SUPPORTED
일부 또는 간접 근거만 확인됨

NOT_OBSERVED
수집 범위에서 근거가 확인되지 않음
거짓이나 미기여를 뜻하지 않음

CONFLICTING
저장소·기간·파일 등 명시적 사실이 사용자 진술과 충돌함
```

커밋이나 PR이 없다는 이유만으로 `CONFLICTING`을 사용하지 않는다.

`NOT_OBSERVED`는 수집 범위에서 관련 근거를 확인하지 못했다는 뜻이다. 대상 기능이나 사용자의 기여가 실제로 존재하지 않는다는 뜻이 아니다.

README 섹션, 테스트, 배포 설정 등의 누락 기반 사실은 AI가 직접 만들지 않는다. 백엔드가 수집 범위와 규칙을 적용하여 `BACKEND_DERIVED` Evidence로 전달한다.

### 10.4 GroundedItem과 ReportItem

`GroundedItem`은 Evidence와 UserClaim 참조를 유지하는 응답 항목의 공통 기반이다. `jobAppeal`과 `portfolioStatements`는 `GroundedItem` 기반 배열로 반환한다.

공통 기반에 필요한 의미는 다음과 같다.

```text
itemId
content
repositoryRefs
evidenceRefs
claimRefs
```

`analysisDepth`, `confidence`, `supportStatus`를 `GroundedItem` 공통 필드에 둘지 각 하위 모델에 둘지는 백엔드의 최종 정상 응답 JSON을 기준으로 확정한다.

AI 결과는 다음 유형으로 구분한다.

```text
OBSERVATION
INTERPRETATION
RECOMMENDATION
INTERVIEW_QUESTION
```

ReportItem 공통 필드:

```text
itemId
reportItemType
content
analysisDepth
repositoryRefs
evidenceRefs
claimRefs
confidence
```

사용자 진술을 평가하는 ReportItem에만 `supportStatus`를 포함한다.

Recommendation은 일반 추천과 저장소 기반 추천으로 종류를 나누지 않는다. 모든 Recommendation은 `evidenceRefs`를 최소 1개 포함해야 한다.

무언가가 관찰되지 않았다는 사실을 기반으로 Recommendation을 생성해야 한다면 Spring Boot가 다음과 같은 명시적인 `BACKEND_DERIVED` Evidence를 전달해야 한다.

```text
README_SECTION_MISSING
TEST_NOT_OBSERVED
DEPLOYMENT_CONFIG_NOT_OBSERVED
```

AI는 누락 여부를 직접 추론하지 않는다.

ReportItem 근거 규칙:

| 유형 | 근거 요구사항 |
|---|---|
| `OBSERVATION` | `evidenceRefs` 필수 |
| `INTERPRETATION` | `evidenceRefs` 또는 `claimRefs` 필수 |
| `RECOMMENDATION` | `evidenceRefs` 최소 1개 필수 |
| 프로젝트 기반 `INTERVIEW_QUESTION` | `evidenceRefs` 또는 `claimRefs` 필수 |

`Confidence`는 사용자 역량이나 사실일 확률이 아니다. 확보된 근거의 직접성과 범위를 나타낸다.

---

## 11. 분석 깊이 규칙

| 깊이 | 허용 판단 | 금지 판단 |
|---|---|---|
| P0 | README 준비도, 기술 근거, 테스트·Docker·CI 존재 | 설계 품질, 사용자 역량, 테스트 품질 |
| P1 | 관찰된 활동, 사용자 진술과 연결되는 활동 영역 | 실제 기여율, 코드 품질, 활동 부재를 거짓으로 판단 |
| P2 | 전달된 코드 구간의 검증·오류 처리·책임 분리·테스트 | 저장소 전체 품질, 경력 수준 충족 여부 |

분석 깊이는 저장소별로 관리한다.

```json
{
  "repositoryFullName": "git-ddo/backend",
  "completedEvidenceLevels": ["P0"],
  "limitations": [
    "코드 근거 분석은 수행되지 않았습니다."
  ]
}
```

최상위 응답에는 요약용 `usedEvidenceLevels`만 둔다. 실제 판단 허용 범위는 저장소별 `completedEvidenceLevels`를 기준으로 검증한다.

계약에는 P0, P1, P2를 모두 정의하지만 MVP 런타임에서는 P0만 지원한다.

```text
P0 요청: 정상 처리
P1 요청: UNSUPPORTED_COMBINATION
P2 요청: UNSUPPORTED_COMBINATION
```

P0 요청과 응답은 `GITHUB_STATIC`, `BACKEND_DERIVED` Evidence만 참조할 수 있다. `GITHUB_ACTIVITY`와 `CODE_EVIDENCE`는 타입만 미리 정의하고 현재 실행하지 않는다.

---

## 12. 백엔드 → AI 요청 계약

최상위 필수 필드:

```text
contractVersion
analysisId
targetJob
targetCareerLevel
analysisPurpose
requestedAnalysisDepth
repositories
```

저장소별 필수 필드:

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

요청 예시의 최소 골격:

```json
{
  "contractVersion": "1.0",
  "analysisId": "86f02adc-9f55-46c7-a498-dc8dca88ef69",
  "targetJob": "BACKEND",
  "targetCareerLevel": "ENTRY",
  "analysisPurpose": "PORTFOLIO_ANALYSIS",
  "requestedAnalysisDepth": "P0",
  "repositories": [
    {
      "repositoryId": 123456789,
      "repositoryFullName": "git-ddo/backend",
      "defaultBranch": "main",
      "snapshotSha": "0123456789abcdef0123456789abcdef01234567",
      "snapshotHashAlgorithm": "SHA1",
      "snapshotSchemaVersion": 1,
      "extractorVersion": "p0-collector-1.0",
      "completedEvidenceLevels": ["P0"],
      "collectionWarnings": [],
      "userClaims": [],
      "evidence": [
        {
          "evidenceId": "ev_001",
          "evidenceType": "GITHUB_STATIC",
          "analysisDepth": "P0",
          "repositoryFullName": "git-ddo/backend",
          "snapshotSha": "0123456789abcdef0123456789abcdef01234567",
          "contentHash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          "summary": "README 파일이 존재합니다.",
          "factKey": "README_EXISTS",
          "value": true,
          "path": "README.md"
        }
      ]
    }
  ]
}
```

---

## 13. AI → 백엔드 응답 계약

최상위 필수 필드:

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

`generationMetadata` 필드:

```text
provider
model
promptVersion
generatedAt
durationMs
attemptCount
tokenUsage
```

확정된 의미는 다음과 같다.

```text
generatedAt  → 생성 완료 시각
durationMs   → AI 요청 전체 처리 시간
attemptCount → 최초 호출을 포함한 provider 시도 횟수
tokenUsage   → 입력·출력 및 합계 토큰 사용량
```

`generatedAt`은 ISO 8601 UTC를 사용하고 `durationMs`는 0 이상의 정수, `attemptCount`는 1 이상의 정수로 정의한다. `tokenUsage`의 정확한 하위 필드와 Gemini의 cached/thought token 포함 여부는 공용 JSON Schema 작성 전에 백엔드와 확정한다.

저장소별 리포트 필수 필드:

```text
repositoryFullName
completedEvidenceLevels
summary
reportItems
limitations
```

### 13.1 `jobAppeal`

`jobAppeal`은 GitHub 및 백엔드에서 수집한 공개 Evidence를 기반으로 확인되는 직무 어필 포인트이다. UserClaim만으로 직무 역량을 단정하지 않는다.

`jobAppeal`은 `GroundedItem` 기반 배열로 반환한다.

각 항목의 최소 필드는 다음과 같다.

```text
itemId
content
repositoryRefs
evidenceRefs
confidence
```

규칙:

- `evidenceRefs`를 최소 1개 포함한다.
- `claimRefs`만 있는 항목은 `jobAppeal`에 포함하지 않는다.
- P0에서는 `GITHUB_STATIC` 또는 `BACKEND_DERIVED` Evidence만 참조한다.
- 파일 존재나 기술 의존성을 사용자의 숙련도 또는 직무 합격 가능성으로 표현하지 않는다.

### 13.2 `portfolioStatements`

`portfolioStatements`는 실제 이력서·포트폴리오·면접 답변에 사용할 수 있는 문장 초안이다.

기존의 단순 문자열 대신 `statementType`을 포함한 `GroundedItem` 기반 배열로 반환한다.

```text
itemId
statementType
content
repositoryRefs
evidenceRefs
claimRefs
```

각 문장은 `evidenceRefs` 또는 `claimRefs` 중 최소 하나를 포함해야 한다. 사용자 역할을 포함한 문장은 UserClaim에 근거했다는 사실을 유지하고 GitHub에서 검증된 사실처럼 표현하지 않는다.

`statementType`은 다음 값만 허용한다.

```text
RESUME
PORTFOLIO
INTERVIEW
```

`itemId`는 `overallDiagnosis`, `repositoryReports`, `representativeProjects`, `jobAppeal`, `roadmap`, `interviewQuestions`, `portfolioStatements` 전체에서 중복되면 안 된다.

`overallDiagnosis`의 개선 항목, Repository별 개선 항목, `roadmap`처럼 행동을 권하는 모든 항목은 동일한 Recommendation 계약을 사용하며 `itemId`와 `evidenceRefs`를 반드시 포함한다.

### 13.3 `validationWarnings`

`validationWarnings`는 응답 전체를 실패시킬 정도가 아닌 비치명적 제한만 표현한다.

```text
제한된 Evidence 범위
수집 경고로 인한 분석 범위 축소
응답을 사용할 수는 있지만 함께 표시해야 하는 한계
```

잘못된 참조, 분석 깊이 위반, 필수 필드 누락, 근거 없는 Recommendation처럼 계약 신뢰성을 깨뜨리는 문제는 warning으로 낮추지 않고 Error Envelope로 전체 실패 처리한다. Warning 객체의 정확한 code, message, JSON Pointer 또는 Repository 참조 필드는 백엔드 정상 응답 JSON을 기준으로 확정한다.

### 13.4 공용 JSON Schema 작성 전 추가 확정 항목

다음 항목은 의미는 합의되었지만 JSON 필드 수준의 계약이 남아 있다. 백엔드의 정상 요청·응답·오류 JSON을 받은 뒤 공용 Fixture와 JSON Schema에 반영한다.

- `GroundedItem`의 정확한 필드, 필수 여부, null 허용 여부
- `repositoryRefs`가 `repositoryId`와 `repositoryFullName` 중 무엇을 참조하는지
- `portfolioStatements`에 `analysisDepth`, `confidence`, `supportStatus`를 포함할지
- `tokenUsage`의 정확한 하위 필드와 Gemini cached/thought token 표현
- `validationWarnings` 항목의 code, message, JSON Pointer 및 Repository 참조 필드
- 오류 `details` 항목의 정확한 필드명과 여러 오류의 정렬·중복 규칙
- Evidence의 타입 구분 필드명과 `DECIMAL`의 JSON 직렬화 방식
- `snapshotSha`의 대소문자와 `snapshotHashAlgorithm`의 적용 범위
- 참여 시작일·종료일의 필수 여부와 날짜 선후 관계
- `BACKEND_DERIVED.sourceEvidenceRefs`의 최소 개수와 관측값 부재 표현

이 항목을 임의로 추정해 Schema를 만들지 않는다.

AI는 백엔드가 계산하지 않은 역량 점수, 기여율 또는 취업 가능성을 새로 생성하지 않는다.

---

## 14. 오류 응답 계약

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

`details`는 JSON Pointer 기반 배열로 반환한다. 각 항목은 최소한 오류 위치를 나타내는 JSON Pointer와 기계 판독 가능한 code, 사용자 또는 개발자가 이해할 수 있는 message를 제공한다. 정확한 필드명과 동일 위치에 여러 오류가 있을 때의 표현 방식은 공용 오류 Fixture에서 확정한다.

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

권장 HTTP 상태:

```text
입력 스키마 오류: 422
지원하지 않는 조합: 400
지원하지 않는 계약 버전: 400
입력 크기 초과: 413
LLM 또는 AI 서버 일시 장애: 502
AI 처리 timeout: 504
```

`retryable`은 참고 정보이다. Spring Boot는 HTTP 상태와 자체 정책을 우선한다.

---

## 15. Job, 중복 실행 및 재시도

### 15.1 Spring Boot 책임

Spring Boot가 다음을 담당한다.

- `analysisId` 생성
- Evaluation Job 생성과 상태 관리
- 동일 `analysisId`의 Job 중복 생성 방지
- 결과 중복 저장 방지
- AI 서버 재호출 정책
- 여러 결과 중 최초로 검증에 성공한 결과 저장

클라이언트 요청의 `Idempotency-Key` 처리 여부와 유효기간도 Spring Boot 영역이다. AI 서버 계약이나 저장소에는 멱등성 상태를 추가하지 않는다.

Spring Boot가 AI 서버를 재호출할 때는 동일한 `analysisId`와 동일한 요청 Snapshot을 사용한다.

### 15.2 AI 서버 책임

AI 서버는 완전 stateless로 유지한다.

```text
요청 수신
→ 요청 검증
→ 독립적인 LLM 실행
→ 결과 검증
→ 응답 반환
```

AI 서버에는 다음을 구현하지 않는다.

```text
Evaluation Job DB
결과 저장소
Redis
Idempotency 저장소
in-memory Job Lock
동일 analysisId 동시 실행 차단
```

네트워크 timeout으로 Spring Boot가 동일 요청을 재호출하면 LLM이 중복 실행될 수 있으며 MVP에서는 이를 허용한다. 같은 입력의 결과가 완전히 동일하다고 보장하지 않는다.

하나의 AI 요청 내부에서 provider의 `429`, timeout, `5xx`를 제한적으로 재시도할 수 있지만, 이는 Job 멱등성이나 중복 실행 방지를 의미하지 않는다.

---

## 16. 검증 책임

### 16.1 AI 서버 검증

```text
Pydantic 요청 검증
→ 요청 의미 검증
→ LLM 호출
→ Pydantic 응답 검증
→ Evidence 참조 검증
→ 분석 깊이 검증
→ 필요 시 1회 재생성
→ 최종 실패 시 오류 반환
```

### 16.2 Spring Boot 최종 검증

```text
응답 JSON Schema 검증
analysisId 일치 확인
Evidence ID allowlist 확인
claimId 확인
repositoryFullName과 snapshotSha 확인
저장소별 completedEvidenceLevels 확인
검증 통과 후 DB 저장
```

MVP에서는 잘못된 일부 항목을 제거해서 저장하지 않는다.

```text
검증 실패
→ 전체 리포트 저장하지 않음
→ Evaluation Job FAILED
```

---

## 17. 보안과 데이터 처리

기본 제한:

```text
README 최대 크기: 256 KiB
일반 텍스트 파일 최대 크기: 128 KiB
백엔드 → AI P0 요청 최대 크기: 2 MiB
바이너리 파일: 제외
생성 코드와 빌드 결과물: 제외
Secret 탐지 값: [REDACTED]
```

기본 제외 디렉터리:

```text
.git
node_modules
dist
build
target
out
coverage
.next
vendor
.venv
__pycache__
```

기본 제외 파일:

```text
.env
.env.*
*.pem
*.key
credentials.*
secrets.*
application-local.*
```

저장 및 로그 정책:

- GitHub raw response를 AI 서버에 전달하지 않는다.
- 저장소 전체 코드를 AI 서버에 전달하지 않는다.
- AI 서버는 README·코드 원문을 영구 저장하지 않는다.
- P2 snippet도 MVP에서는 영구 저장하지 않는다.
- LLM 요청·응답 전문을 운영 로그에 남기지 않는다.
- 로그에는 `analysisId`, 처리 단계, 처리 시간, Evidence 개수, 토큰 사용량, 오류 코드만 남긴다.
- snippet을 저장하지 않아도 `snapshotSha`, `path`, `startLine`, `endLine`, `contentHash`는 보존한다.
- 저장소가 삭제되거나 비공개로 전환되면 과거 Evidence를 재확인하지 못할 수 있음을 리포트 한계에 포함한다.

---

## 18. 목표 프로젝트 구조

```text
gitddo/
├── docs/
│   ├── contracts/
│   │   ├── README.md
│   │   ├── analysis-request.schema.json
│   │   ├── analysis-response.schema.json
│   │   ├── error-response.schema.json
│   │   └── fixtures/
│   │       ├── valid-analysis-request.json
│   │       ├── valid-analysis-response.json
│   │       ├── invalid-evidence-reference.json
│   │       └── unsupported-analysis-depth.json
│   ├── guide.md
│   └── github-workflow.md
│
└── ai/
    ├── app/
    │   ├── schemas/
    │   │   ├── common.py
    │   │   ├── enums.py
    │   │   ├── evidence.py
    │   │   ├── claims.py
    │   │   ├── repository.py
    │   │   ├── request.py
    │   │   ├── response.py
    │   │   └── error.py
    │   ├── validators/
    │   │   ├── evidence_validator.py
    │   │   ├── depth_validator.py
    │   │   └── report_validator.py
    │   └── ...
    ├── scripts/
    │   └── export_contracts.py
    └── tests/
        ├── test_common.py
        ├── test_request_schema.py
        ├── test_response_schema.py
        ├── test_error_schema.py
        ├── test_evidence_validator.py
        └── test_depth_validator.py
```

공용 계약 Fixture는 `docs/contracts/fixtures`에서 관리한다. `ai/tests/fixtures`에는 Prompt Injection이나 LLM 실패처럼 AI 서버에만 필요한 Fixture만 둔다.

---

## 19. 단계별 실행 계획

각 Phase는 독립적으로 검증 가능한 작업 단위이다. 백엔드와 AI의 독립 Phase는 병렬로 진행할 수 있으며, 실제 연동은 양쪽 독립 완료 조건을 만족한 뒤 시작한다.

### 현재 실행 순서

```text
Phase 0  최소 계약 의미와 책임 경계 확정
Phase 1  AI 독립 기반: P0 Criteria · System Prompt · Gemini Provider
Phase 2  백엔드 독립 기반: P0 Collector · Evidence · Job
Phase 3  AI 내부 P0 분석 파이프라인
Phase 4  양쪽 독립 검증
Phase 5  실제 데이터를 기준으로 최종 DTO · Schema · Fixture 확정
Phase 6  양쪽 계약 Validator
Phase 7  Mock HTTP 연동
Phase 8  실제 Gemini · Spring Boot E2E
```

Fixture 선확정은 요구하지 않는다. AI는 wire DTO와 분리된 내부 모델로 먼저 개발하고, 백엔드는 Fake AI Client로 먼저 개발한다. 양쪽에서 필요한 데이터가 확인된 뒤 Pydantic·Java DTO를 확정하고 공용 Fixture를 생성한다.

아래의 기존 계약 마이그레이션 작업 목록은 Phase 5~7에서 수행할 세부 체크리스트로 사용한다. 목록에 붙은 기존 Phase 번호는 작업 종류를 구분하기 위한 참조이며 현재 실행 우선순위를 의미하지 않는다.

### Phase 0. 현재 상태 점검

작업:

- [ ] `git status --short --branch` 확인
- [ ] 기존 변경 및 미추적 파일 확인
- [ ] Phase 1 동작 확인
- [ ] 현재 테스트 결과 기록
- [ ] 기존 Phase 2 계약 파일 목록 확인

검증:

```bash
cd ai
pytest
ruff check .
ruff format --check .
mypy app
```

완료 조건:

- 기존 상태와 실패 여부가 기록됨
- 사용자 변경을 덮어쓰지 않음

이 Phase에서는 커밋하지 않는다.

---

### 기존 계약 작업 A. 계약 문서 재작성

목표:

- 코드 변경 전에 백엔드와 AI가 공유할 의미와 경계를 문서로 고정

작업:

- [ ] `docs/contracts/README.md` 생성
- [ ] Evidence, UserClaim, ReportItem 의미 작성
- [ ] GroundedItem과 `statementType` 의미 작성
- [ ] API 경로와 버전 정책 작성
- [ ] 분석 깊이 허용 판단표 작성
- [ ] enum 전체와 MVP 허용값 작성
- [ ] 오류 코드 작성
- [ ] 생성 메타데이터, 비치명적 Warning, JSON Pointer 오류 상세 규칙 작성
- [ ] Snapshot hash 알고리즘, 참여 기간, Evidence value 타입 규칙 작성
- [ ] 보안과 입력 제한 작성
- [ ] `docs/guide.md`의 기존 대형 계약 예시를 공용 계약 문서 링크로 교체
- [ ] Phase 2 완료 체크를 재설계 상태로 변경
- [ ] MVP 완료 기준을 `BACKEND × ENTRY × PORTFOLIO_ANALYSIS × P0`로 수정

검증:

- 문서 내부 필드명이 `contractVersion`으로 통일됨
- `schemaVersion`과 정수 `analysisId` 예시가 남아 있지 않음
- `USER_PROVIDED`, `AI_RECOMMENDATION`이 EvidenceType에 남아 있지 않음
- AnalysisPurpose가 `PORTFOLIO_ANALYSIS`로 통일됨
- AI 서버에 Job Lock이나 결과 저장 책임이 남아 있지 않음

권장 커밋:

```text
docs: 평가 계약 v1.0 설계 반영
```

---

### 기존 계약 작업 B. Pydantic 계약 재설계

목표:

- 기존 Phase 2 Pydantic 모델을 최종 합의 계약으로 교체

수정·생성 파일:

```text
ai/app/schemas/common.py
ai/app/schemas/enums.py
ai/app/schemas/evidence.py
ai/app/schemas/claims.py
ai/app/schemas/repository.py
ai/app/schemas/request.py
ai/app/schemas/response.py
ai/app/schemas/error.py
```

작업:

- [ ] `ApiModel`과 공통 제약 타입 정리
- [ ] 전체 enum 구현
- [ ] Evidence 모델 구현
- [ ] UserClaim 모델 구현
- [ ] 저장소 Snapshot 및 수집 범위 모델 구현
- [ ] Snapshot hash 알고리즘과 hash 길이 제약 구현
- [ ] 참여 기간 ISO date 및 null 제약 구현
- [ ] Evidence value 타입별 제약과 자유 형식 object 거절 구현
- [ ] UUID 기반 요청 모델 구현
- [ ] ReportItem 및 GroundedItem 기반 응답 모델 구현
- [ ] `jobAppeal` Evidence 기반 응답 모델 구현
- [ ] `statementType`과 참조를 포함하는 `portfolioStatements` 모델 구현
- [ ] `generationMetadata`, `tokenUsage`, `validationWarnings` 모델 구현
- [ ] Error Envelope 구현
- [ ] JSON Pointer 기반 오류 `details` 모델 구현
- [ ] 저장소 1~5개 제한 적용
- [ ] 알 수 없는 필드 거절 유지
- [ ] 기존 계약 테스트를 새 계약에 맞게 교체
- [ ] ID 형식 제약 구현

기존 제거 대상 개념:

```text
schemaVersion
정수 analysisId
EvidenceType.GITHUB
EvidenceType.USER_PROVIDED
EvidenceType.AI_RECOMMENDATION
GitHubEvidence에 P0와 P1을 혼합한 구조
문자열 경로 배열을 직접 evidence로 반환하는 구조
근거 없는 Recommendation
단순 문자열 portfolioStatements
```

검증:

```bash
cd ai
pytest tests/test_common.py tests/test_request_schema.py tests/test_response_schema.py tests/test_error_schema.py
ruff check .
ruff format --check .
mypy app
```

완료 조건:

- 정상 요청·응답·오류 Fixture 검증 성공
- 잘못된 UUID, enum, 필수 필드, 저장소 개수, Evidence value 검증 실패
- `jobAppeal`과 `portfolioStatements`가 합의된 GroundedItem 계약을 따름
- 생성 메타데이터와 Warning 및 오류 상세가 합의된 wire format을 따름
- 기존 계약을 참조하는 테스트가 남아 있지 않음

권장 커밋:

```text
feat: 평가 API 계약 v1.0 재설계
```

---

### 기존 계약 작업 C. 공용 Fixture와 JSON Schema 생성

목표:

- Java DTO와 Pydantic 모델이 동일 계약을 사용하도록 공용 산출물 제공

작업:

- [ ] `docs/contracts/fixtures` 생성
- [ ] 정상 요청 Fixture 작성
- [ ] 정상 응답 Fixture 작성
- [ ] 비치명적 `validationWarnings`를 포함한 정상 응답 Fixture 작성
- [ ] JSON Pointer `details`를 포함한 오류 Fixture 작성
- [ ] 잘못된 Evidence 참조 Fixture 작성
- [ ] 잘못된 Evidence value와 Snapshot hash 조합 Fixture 작성
- [ ] 지원하지 않는 깊이 Fixture 작성
- [ ] `ai/scripts/export_contracts.py` 작성
- [ ] Pydantic 모델에서 Draft 2020-12 JSON Schema 생성
- [ ] AI 테스트가 공용 Fixture를 읽도록 변경
- [ ] 생성 Schema를 직접 수정하지 않는 규칙 문서화

생성 파일:

```text
docs/contracts/analysis-request.schema.json
docs/contracts/analysis-response.schema.json
docs/contracts/error-response.schema.json
```

완료 조건:

- Schema 재생성 결과에 불필요한 diff가 없음
- 정상 Fixture는 Schema 검증 성공
- 실패 Fixture는 예상 규칙에서 검증 실패
- 백엔드가 같은 Schema와 Fixture로 DTO 테스트 가능

권장 커밋:

```text
build: 평가 계약 JSON Schema 생성 체계 추가
```

---

### 기존 계약 작업 D. 요청 의미 검증

목표:

- Pydantic 형태 검증만으로 확인할 수 없는 참조 및 깊이 규칙 검증

작업:

- [ ] Evidence ID 중복 검출
- [ ] Claim ID 중복 검출
- [ ] `sourceEvidenceRefs` 존재 검증
- [ ] `relatedEvidenceRefs` 존재 검증
- [ ] Snapshot SHA 일치 검증
- [ ] `snapshotHashAlgorithm`과 Snapshot SHA 길이 일치 검증
- [ ] `contentHash` SHA-256 형식 검증
- [ ] Evidence `valueType`과 실제 value 타입 일치 검증
- [ ] Evidence 자유 형식 object value 거절
- [ ] 참여 기간 날짜 선후 관계 검증
- [ ] `completedEvidenceLevels`와 Evidence 깊이 일치 검증
- [ ] MVP 지원 조합 검증
- [ ] `repositoryId` 양의 정수 검증
- [ ] `evidenceId`와 `claimId`의 analysis 전역 중복 검증

검증 책임 분리:

```text
Pydantic
타입, UUID, enum, 길이, 배열 크기, hash 형식

Validator
참조 무결성, Snapshot 관계, 분석 깊이, 지원 조합, ID 전역 유일성
```

완료 조건:

- 존재하지 않는 참조와 Snapshot 불일치를 거절
- hash 알고리즘과 길이가 다르거나 Evidence value 타입이 다르면 거절
- 참여 종료일이 시작일보다 빠르면 거절
- P0 요청에 P1/P2 Evidence가 들어오면 거절
- P1/P2 요청을 `UNSUPPORTED_COMBINATION`으로 변환
- `BACKEND × ENTRY × PORTFOLIO_ANALYSIS × P0` 이외 조합을 거절

권장 커밋:

```text
feat: 평가 요청 의미 검증 추가
```

---

### 기존 계약 작업 E. 응답 Evidence 및 깊이 검증

목표:

- AI 결과가 허용된 근거와 분석 깊이 안에서만 생성되도록 보장

작업:

- [ ] 응답 `analysisId` 일치 검증
- [ ] Repository allowlist 검증
- [ ] Evidence ref allowlist 검증
- [ ] Claim ref allowlist 검증
- [ ] 저장소별 분석 깊이 검증
- [ ] Observation Evidence 필수 규칙 구현
- [ ] Interpretation Evidence 또는 Claim 필수 규칙 구현
- [ ] 모든 Recommendation의 Evidence 최소 1개 규칙 구현
- [ ] `jobAppeal`의 Evidence 최소 1개 및 Claim 단독 사용 금지 구현
- [ ] `portfolioStatements`의 Evidence 또는 Claim 최소 1개 규칙 구현
- [ ] `portfolioStatements.statementType` 허용값 검증
- [ ] `validationWarnings`에 비치명적 제한만 포함되는지 검증
- [ ] `generationMetadata`의 시각·처리 시간·시도 횟수·tokenUsage 검증
- [ ] 응답 전체 `itemId` 중복 검출
- [ ] `NOT_OBSERVED` 의미 위반 검출
- [ ] 개인 실력·취업 가능성·기여율 단정 검출
- [ ] 검증 실패 시 전체 리포트 실패 처리

완료 조건:

- 잘못된 일부 항목을 제거해 성공 처리하지 않음
- 존재하지 않는 기술·파일·Evidence를 참조한 리포트 거절
- P0 저장소에 대한 P1/P2 판단 거절
- 근거 없는 Recommendation과 `jobAppeal` 거절
- 참조 없는 포트폴리오 문장 거절
- 치명적 계약 위반을 Warning으로 낮춘 응답 거절

권장 커밋:

```text
feat: 리포트 근거 및 분석 깊이 검증 추가
```

---

### 기존 계약 작업 F. Mock 내부 API 구현

목표:

- LLM 없이 Spring Boot와 계약 기반 연동 가능

수정 파일:

```text
ai/app/api/reports.py
ai/app/main.py
ai/app/core/exceptions.py
```

처리 흐름:

```text
Pydantic 요청 검증
→ 요청 의미 검증
→ 고정 Fixture 응답 생성
→ 응답 Validator
→ 200 OK
```

작업:

- [ ] `POST /internal/v1/portfolio-reports` 구현
- [ ] Reports Router를 FastAPI 앱에 등록
- [ ] 공통 Error Envelope 적용
- [ ] 저장소 1개와 5개 테스트
- [ ] 잘못된 UUID와 enum 테스트
- [ ] 지원하지 않는 조합 테스트
- [ ] Evidence ID 중복 테스트
- [ ] Snapshot 불일치 테스트
- [ ] 요청 크기 초과 테스트

완료 조건:

- Spring Boot가 LLM 없이 요청·응답 통합 테스트 가능
- 모든 실패가 Error Envelope로 반환됨

권장 커밋:

```text
feat: 평가 리포트 Mock API 구현
```

---

### 기존 계약 작업 G. 보안과 입력 제한 적용

목표:

- P0 데이터를 LLM에 전달하기 전에 최소 보안 경계 적용

수정 파일:

```text
ai/app/core/config.py
ai/.env.example
ai/app/prompts/system.py
관련 API 및 테스트
```

환경변수:

```env
MAX_REPOSITORIES=5
MAX_REQUEST_BYTES=2097152
```

P2 예산 관련 환경변수는 P2 런타임 지원을 시작하는 Phase에서 추가한다. 현재는 계약 enum만 정의하고 P2 요청을 거절한다.

작업:

- [ ] 요청 전체 크기 제한
- [ ] 민감 원문 로그 금지
- [ ] untrusted data 직렬화 경계 정의
- [ ] Prompt Injection 방어 System Prompt 작성
- [ ] README와 사용자 입력의 지시문 무시 테스트
- [ ] 코드 비실행 원칙 문서화
- [ ] 로그 마스킹 테스트

완료 조건:

- 2 MiB 초과 요청 거절
- README·코드·사용자 입력 전문이 로그에 남지 않음
- 외부 입력이 Prompt 규칙을 변경하지 못함

권장 커밋:

```text
feat: 평가 요청 보안 및 크기 제한 적용
```

---

### 기존 계약 작업 H. 문서 및 에이전트 지침 동기화

목표:

- 실제 구현과 모든 프로젝트 문서를 동일 상태로 맞춤

수정 대상:

```text
AGENTS.md
README.md
ai/README.md
docs/guide.md
docs/github-workflow.md
```

작업:

- [ ] Evidence, UserClaim, ReportItem 분리 반영
- [ ] UUID `analysisId` 반영
- [ ] 네 가지 버전 분리 반영
- [ ] `BACKEND × ENTRY × PORTFOLIO_ANALYSIS × P0` 범위 반영
- [ ] `jobAppeal` 및 `portfolioStatements` 계약 반영
- [ ] 저장소별 분석 깊이 반영
- [ ] AI와 Spring Boot 이중 검증 반영
- [ ] Error Envelope 반영
- [ ] Spring Boot Job 책임과 AI stateless 정책 반영
- [ ] 보안 제한 반영
- [ ] 실제 완료된 Phase만 체크

완료 조건:

- 문서와 구현의 필드명·enum·경로가 일치
- 오래된 요청·응답 JSON이 남아 있지 않음
- 현재 미지원 기능을 완료로 표시하지 않음

권장 커밋:

```text
docs: 평가 계약 구현 상태와 개발 가이드 동기화
```

---

## 20. 필수 테스트 목록

### 20.1 계약 테스트

- [ ] `contractVersion`은 `1.0`만 허용
- [ ] `analysisId`는 UUID v4만 허용
- [ ] `repositoryId`는 GitHub numeric ID로 검증
- [ ] `evidenceId`, `claimId`, `itemId` 형식 검증
- [ ] 저장소 1개와 5개 허용
- [ ] 저장소 0개와 6개 거절
- [ ] 알 수 없는 필드 거절
- [ ] 현재 미지원 enum 조합 거절
- [ ] `PORTFOLIO_ANALYSIS` 이외 분석 목적 거절
- [ ] `snapshotHashAlgorithm`은 `SHA1`, `SHA256`만 허용
- [ ] 알고리즘에 따라 Snapshot SHA 길이 검증
- [ ] 참여 기간은 ISO date 또는 null만 허용

### 20.2 Evidence 테스트

- [ ] Evidence ID 중복 거절
- [ ] Claim ID 중복 거절
- [ ] Repository가 달라도 Evidence ID와 Claim ID를 다시 사용하면 거절
- [ ] 잘못된 `contentHash` 거절
- [ ] 존재하지 않는 Evidence 참조 거절
- [ ] Snapshot SHA 불일치 거절
- [ ] `BACKEND_DERIVED` 원본 근거 누락 거절
- [ ] Evidence value는 `STRING`, `BOOLEAN`, `INTEGER`, `DECIMAL`, `STRING_LIST`만 허용
- [ ] Evidence value와 `valueType` 불일치 거절
- [ ] 자유 형식 object 및 중첩 object value 거절

### 20.3 분석 깊이 테스트

- [ ] P0 입력에 P1 Activity Evidence가 있으면 거절
- [ ] P0 입력에 P2 Code Evidence가 있으면 거절
- [ ] P0 리포트에서 코드 품질 판단을 생성하면 거절
- [ ] 저장소마다 다른 `completedEvidenceLevels` 허용

### 20.4 ReportItem 테스트

- [ ] Observation에 Evidence가 없으면 거절
- [ ] Interpretation에 Evidence와 Claim이 모두 없으면 거절
- [ ] 모든 Recommendation은 Evidence 최소 1개 필수
- [ ] `jobAppeal`은 Evidence 최소 1개 필수
- [ ] UserClaim만 참조한 `jobAppeal` 거절
- [ ] 모든 `portfolioStatements` 항목은 Evidence 또는 Claim 최소 1개 필수
- [ ] `portfolioStatements.statementType`의 잘못된 enum 거절
- [ ] `jobAppeal`과 `portfolioStatements`가 GroundedItem 공통 계약을 따름
- [ ] 응답 전체 Item ID 중복 거절
- [ ] 프로젝트 기반 InterviewQuestion은 근거 또는 Claim 필수
- [ ] `NOT_OBSERVED`를 거짓으로 표현하면 거절

### 20.5 오류 테스트

- [ ] 모든 오류가 공통 Envelope 사용
- [ ] `analysisId`를 알 수 없는 경우 `null` 허용
- [ ] 오류 `details`가 유효한 JSON Pointer 기반 배열인지 검증
- [ ] `retryable`과 HTTP 상태 조합 검증
- [ ] 검증 실패 리포트를 부분 저장하지 않음
- [ ] `validationWarnings`에는 비치명적 제한만 허용
- [ ] `generationMetadata`의 생성 시각, 처리 시간, 시도 횟수, tokenUsage 검증

### 20.6 보안 테스트

- [ ] Prompt Injection 입력 무시
- [ ] Secret 패턴 마스킹
- [ ] 원문 로그 미출력
- [ ] 요청 크기 제한
- [ ] 코드 실행 경로 없음

---

## 21. 전체 검증 명령

각 Phase 완료 시 현재 환경에 존재하는 검증을 실행한다.

```bash
cd ai
pytest
ruff check .
ruff format --check .
mypy app
docker build -t gitddo-ai .
```

계약 변경 시 추가 확인:

```text
JSON Schema 재생성 후 예상하지 않은 diff가 없는가
공용 정상 Fixture가 요청·응답 Schema를 통과하는가
공용 실패 Fixture가 예상 지점에서 실패하는가
Pydantic 직렬화 결과가 camelCase 계약과 일치하는가
```

실행하지 못한 검증이 있으면 생략하지 말고 이유와 실행 방법을 보고한다.

---

## 22. 권장 커밋 순서

```text
AI 독립 개발
1. feat: Backend P0 Criteria 추가
2. feat: 근거 기반 System Prompt 추가
3. feat: Gemini Provider 기반 구현
4. feat: P0 포트폴리오 분석 파이프라인 추가

계약 확정과 연동
5. docs: 평가 계약 v1.0 wire format 확정
6. feat: 평가 API 계약 v1.0 재설계
7. build: 평가 계약 JSON Schema와 Fixture 추가
8. feat: 평가 요청 의미 검증 추가
9. feat: 리포트 근거 및 분석 깊이 검증 추가
10. feat: 평가 리포트 Mock API 구현
11. feat: 평가 요청 보안 및 크기 제한 적용
12. docs: 평가 계약 구현 상태와 개발 가이드 동기화
```

각 커밋에는 해당 작업과 직접 관련된 파일만 포함한다. 사용자나 다른 에이전트의 변경을 함께 커밋하지 않는다.

---

## 23. 중단 및 보고 조건

다음 상황에서는 임의로 구현하지 말고 작업을 중단한 뒤 사용자에게 보고한다.

- 백엔드 DTO와 본 계약의 필드가 다름
- `ParticipationLevel` 허용값이 백엔드와 다름
- AI 서버에 Job 저장, Redis, 실행 Lock 또는 결과 중복 저장 책임이 요구됨
- Snapshot SHA 또는 Evidence ID 생성 규칙이 다름
- P0 요청에 코드 원문 전체가 포함됨
- JSON Schema와 Pydantic 모델이 다름
- 기존 사용자 변경과 같은 파일에서 충돌함
- 검증 실패를 해결하려면 계약 의미를 바꿔야 함

보고 내용에는 다음을 포함한다.

```text
충돌한 파일 또는 필드
현재 문서 기준
현재 구현 기준
가능한 선택지
각 선택지의 영향
추천 선택지
```

---

## 24. 최종 완료 기준

- [ ] 백엔드와 AI가 동일한 JSON Schema와 Fixture를 사용함
- [ ] `analysisId`가 UUID v4이며 Repository·Evidence·Claim·Item ID 규칙이 적용됨
- [ ] Evidence, UserClaim, ReportItem이 분리됨
- [ ] `contractVersion`과 Snapshot·Extractor·Prompt 버전이 분리됨
- [ ] `snapshotHashAlgorithm`과 Snapshot SHA 형식이 일치함
- [ ] 참여 기간이 ISO date 또는 null로 직렬화됨
- [ ] Evidence value가 합의된 다섯 타입으로 제한되고 자유 형식 object가 거절됨
- [ ] 저장소별 `completedEvidenceLevels`와 `limitations`가 존재함
- [ ] `jobAppeal`이 공개 Evidence만을 기반으로 함
- [ ] 모든 Recommendation이 Evidence를 참조함
- [ ] `jobAppeal`과 `portfolioStatements`가 GroundedItem 기반 배열임
- [ ] 모든 포트폴리오 문장이 유효한 `statementType`과 Evidence 또는 Claim을 포함함
- [ ] `generationMetadata`에 provider, model, promptVersion, 생성 시각, 처리 시간, 시도 횟수, tokenUsage가 포함됨
- [ ] `validationWarnings`가 비치명적 제한만 표현함
- [ ] 오류 `details`가 JSON Pointer 기반 배열임
- [ ] AI 서버가 DB, Redis, Job Lock 없이 stateless로 동작함
- [ ] P0 판단 범위를 넘는 결과를 Validator가 차단함
- [ ] AI와 Spring Boot의 이중 검증 경계가 문서화됨
- [ ] Error Envelope가 모든 AI API 오류에 적용됨
- [ ] 보안 제외 파일과 입력 크기 제한이 적용됨
- [ ] Mock API를 통해 Spring Boot 통합 테스트가 가능함
- [ ] 전체 pytest, Ruff, mypy, Docker 검증이 통과함
- [ ] 모든 문서가 실제 구현과 일치함

Gemini Provider와 P0 Prompt·Criteria는 최종 DTO 전에 독립 구현할 수 있다. 다만 실제 Spring Boot 요청, 최종 Structured Output, Evidence Validator 및 결과 저장을 연결하는 E2E는 이 완료 기준을 충족한 뒤 진행한다.
