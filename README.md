# GitDdo

GitDdo는 공개 GitHub Repository에서 확인되는 근거와 사용자가 입력한 역할·경험을 분리해
포트폴리오 어필 포인트, 보완 방향과 면접 준비 자료를 만드는 AI 코칭 서비스이다.

사용자의 실력, 개인 기여율, 경력 수준 충족 여부 또는 취업 가능성을 자동 채점하지 않는다.

## 서비스 흐름

```text
Frontend
  Repository 선택 · 역할/목표 입력 · 진행 상태/결과 표시
        ↓
Spring Boot Backend
  GitHub OAuth · Snapshot 고정 · P0/P1/P2 Evidence 수집
  Evaluation Job · AI 요청 조립 · 최종 응답 검증/저장
        ↓ POST /internal/v1/portfolio-reports
FastAPI AI Server
  Evidence/UserClaim 해석 · Gemini Structured Output
  참조/깊이/정책 검증 · 코칭 리포트 반환
```

## 분석 깊이

| 깊이 | 입력 근거 | AI가 설명할 수 있는 범위 |
| --- | --- | --- |
| P0 | README, 메타데이터, 파일 트리, 언어, 빌드·테스트·Docker·Actions 설정 | 문서 준비도, 기술·구성의 관찰 여부 |
| P1 | 커밋, PR, 변경 경로와 최근 활동 | 관찰된 활동 영역, UserClaim과 연결 가능한 활동 근거 |
| P2 | Backend가 선별한 제한된 코드·테스트 snippet | 제공된 코드 구간의 검증·오류 처리·책임과 테스트 사례 |

P1 활동량은 실력이나 기여율이 아니다. P2 코드 구간도 Repository 전체 품질이나 아키텍처를
대표하지 않는다.

## 계약 기준

실제 Wire Contract의 Source of Truth는 Backend 저장소의 다음 파일이다.

```text
backend/backend/docs/contracts/analysis-request.schema.json
backend/backend/docs/contracts/analysis-response.schema.json
backend/backend/docs/contracts/analysis-error.schema.json
```

현재 계약의 핵심 값은 다음과 같다.

```text
schemaVersion: "1.0"
Repository: 1~5개
TargetJob: BACKEND, FRONTEND, AI, CLOUD_INFRA
TargetCareerLevel: ENTRY, JUNIOR, MID, SENIOR
AnalysisPurpose: PORTFOLIO_ANALYSIS
AnalysisDepth: P0, P1, P2
repositoryId: string
EvidenceType: GITHUB_STATIC, GITHUB_ACTIVITY, CODE_EVIDENCE, BACKEND_DERIVED
```

Schema가 표현하는 enum과 실제 분석 구현 범위는 다르다. 현재 개발 목표는
`BACKEND × ENTRY × PORTFOLIO_ANALYSIS × P0/P1/P2`이며, 다른 직무와 경력 수준 분석은
후속 범위이다.

## 현재 개발 상태

| 영역 | 상태 |
| --- | --- |
| Backend `main` | P0/P1 수집, Mock AI, 응답 검증과 Job 저장 흐름 구현 |
| Backend P2 | `origin/feat/portfolio-evaluation-p2`의 `bcc9a4f`에서 코드 snippet 수집 구현, 아직 `main` 미병합 |
| AI 기반 | FastAPI, `/health`, Gemini/Fake Provider, P0/P1/P2 Criteria와 혼합 깊이 System Prompt 구현 |
| AI 입력 처리 | 내부 Evidence·UserClaim 모델, 정규화, Prompt Context, 참조·깊이 Validator 구현 |
| AI 분석 코어 | Repository 분석, Portfolio 종합, 면접 질문, 포트폴리오 문장과 정책 재생성 구현 |
| AI 최종 내부 결과 | 검증 완료 결과를 결정적으로 조립하는 `PortfolioAnalysisAssembler` 구현 |
| AI 서버 오케스트레이션 | Report Service, 전체 600초 deadline과 generation metadata 집계 구현 |
| 실제 Gemini Smoke | `gemini-3.5-flash-lite`로 Repository 1개 P0/P1/P2 정식 파이프라인 완주 |
| 실제 연동 | Backend 기준 Wire DTO·Error Envelope와 리포트 API 구현 후 진행 예정 |

Backend P2 브랜치는 저장소당 최대 8개, snippet당 최대 40줄·4,000자, 원본 파일 최대
80,000 byte 제한을 적용한다. 전체 요청 기준 snippet·token 예산과 P2 대상 저장소 제한은
아직 Backend 추가 합의가 필요하다.

## 주요 결과 계약

- Repository별 `findings`
- 전체 포트폴리오 기준 단일 `jobAppeal`
- Evidence 기반 `strengths`, `gaps`, `nextActions`
- Evidence 또는 UserClaim을 참조하는 `portfolioStatements`
- Evidence 또는 UserClaim을 참조하는 `interviewQuestions`
- 수집·분석 범위를 설명하는 `limitations`

현재 Backend Schema에는 `portfolioStatements.type`, 문장·질문의 `repositoryId`,
`followUpQuestions`가 없다. 해당 필드는 Backend Schema가 변경되기 전 현재 계약으로 취급하지
않는다.

## 기술 스택

### Frontend

- React, TypeScript, Vite
- TanStack Query, Tailwind CSS

### Backend

- Java 21, Spring Boot
- Spring Security OAuth2, Spring Data JPA
- PostgreSQL, Docker

### AI

- Python 3.12+, FastAPI, Pydantic v2
- Google Gen AI SDK, Gemini Structured Output
- PyYAML, tenacity
- pytest, Ruff, mypy, Docker

MVP에서는 LangChain, RAG, Vector Database, Fine-tuning 또는 자체 ML 모델을 사용하지 않는다.

## 문서

- [평가 의미와 계약 설계 원칙](./EVALUATION_CONTRACT_MIGRATION_GUIDE.md)
- [AI 서버 개발 순서](./docs/guide.md)
- [AI 서버 실행과 현재 상태](./ai/README.md)
- [GitHub 협업 규칙](./docs/github-workflow.md)
- [AI 에이전트 작업 규칙](./AGENTS.md)

## 다음 작업

AI의 내부 Report Service 구현은 완료됐다.

```text
입력 참조·깊이 검증
→ Repository 정규화와 분석
→ Portfolio synthesis
→ InterviewQuestion·PortfolioStatement 생성
→ PortfolioAnalysis 최종 조립
→ generation metadata 집계
→ InternalPortfolioReport
```

Report Service는 Repository 하나의 필수 분석이 실패하면 전체 분석을 실패시키고, Gemini
호출·Provider retry·정책 재생성을 모두 포함하는 600초 전체 deadline을 적용한다. 다음으로 기존
`ai/app/schemas/` 초안을 Backend JSON Schema 기준으로 교체하고 Error Envelope,
`POST /internal/v1/portfolio-reports`, Fake Provider 기반 HTTP E2E를 순서대로 구현한다.

실제 Gemini 내부 파이프라인 검증 기록은
[`docs/gemini-smoke-test.md`](./docs/gemini-smoke-test.md)에 정리한다. 최종 Wire API와 Spring
Boot E2E는 아직 검증 범위에 포함되지 않는다.
