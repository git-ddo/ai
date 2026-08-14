# GitDdo AI Server

공개 GitHub Repository에서 확인되는 근거와 사용자 진술을 분리하여 포트폴리오 어필 포인트, 보완 방향, 면접 준비 자료를 생성하는 AI 코칭 서버이다.

GitDdo는 사용자의 실력·기여율·취업 가능성을 자동 채점하지 않는다.

## 현재 MVP

```text
계약 버전: 1.0
평가 저장소: 1~5개
지원 조합: BACKEND × ENTRY × PORTFOLIO_ANALYSIS × P0
```

`P1`, `P2`, 다른 직무 및 경력 수준은 계약 확장을 위해 enum으로 정의할 수 있지만 현재 런타임에서는 `UNSUPPORTED_COMBINATION`으로 거절한다.

## 주요 결과

- 전체 포트폴리오 진단
- Repository별 P0 분석과 한계
- 대표 프로젝트 추천
- 공개 근거 기반 `jobAppeal`
- 근거 기반 개선 Recommendation
- 이력서·포트폴리오·면접용 `portfolioStatements`
- 예상 면접 질문과 답변 가이드

## 핵심 계약

```text
Evidence
GitHub 또는 백엔드가 확인·도출한 사실

UserClaim
사용자가 직접 입력한 역할과 경험

ReportItem
AI가 생성한 관찰·해석·추천·면접 질문
```

- 사용자 진술은 Evidence가 아니다.
- AI 추천은 Evidence가 아니다.
- 모든 Recommendation은 `evidenceRefs`를 최소 1개 가져야 한다.
- `jobAppeal`은 공개 Evidence만을 근거로 하며 Claim만으로 확정하지 않는다.
- `portfolioStatements`는 `evidenceRefs` 또는 `claimRefs` 중 최소 하나를 가져야 한다.
- `NOT_OBSERVED`는 수집 범위에서 확인되지 않았다는 뜻이며 부재·거짓·미기여를 뜻하지 않는다.

## 데이터 흐름

```text
Spring Boot
  Snapshot 고정 · P0 Evidence/UserClaim 구성 · Job 관리
        ↓ POST /internal/v1/portfolio-reports
FastAPI AI Server
  요청 검증 · Gemini 호출 · 참조/깊이/응답 검증
        ↓ 구조화 JSON 또는 Error Envelope
Spring Boot
  최종 검증 · 결과 저장 · Frontend 제공
```

AI 서버는 GitHub API, 사용자 인증, Evaluation Job, 결과 저장 및 멱등성 상태를 관리하지 않는다. DB, Redis, in-memory Job Lock 없이 stateless로 동작한다.

## 기술 스택

- Python 3.12+
- FastAPI, Uvicorn
- Pydantic v2, pydantic-settings
- Google Gen AI SDK와 Gemini Structured Output
- pytest, Ruff, mypy
- Docker, GitHub Actions

MVP에서는 LangChain, RAG, Vector Database, Fine-tuning 및 자체 ML 모델을 사용하지 않는다.

## 문서

- [평가 계약 마이그레이션 최종 기준](./EVALUATION_CONTRACT_MIGRATION_GUIDE.md)
- [AI 서버 개발 가이드](./docs/guide.md)
- [AI 서버 실행 및 구조](./ai/README.md)
- [GitHub 협업 규칙](./docs/github-workflow.md)
- [AI 에이전트 작업 규칙](./AGENTS.md)

공용 계약 구현 후 `docs/contracts/`에서 계약 의미, JSON Schema 및 Fixture를 관리한다.

## 현재 개발 상태

- Phase 1 기반 환경과 `/health` 구현 완료
- 최종 `contractVersion = "1.0"`에 맞춘 문서 동기화 진행
- 백엔드와 AI가 Fake·Stub으로 각자의 P0 기능을 먼저 개발하는 순서로 전환
- AI는 P0 Criteria·System Prompt·Gemini Provider·내부 분석 파이프라인부터 구현 예정
- 백엔드는 P0 Collector·Evidence·Job 흐름을 AI 서버 없이 구현 예정
- 기존 Pydantic 계약은 최종 계약으로 마이그레이션 필요
- 최종 DTO·Schema·Fixture, Mock 연동과 E2E는 독립 개발 이후 진행

실제 완료 상태와 다음 작업은 [AI 서버 개발 가이드](./docs/guide.md)를 기준으로 확인한다.
