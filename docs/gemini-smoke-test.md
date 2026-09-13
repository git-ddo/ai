# Gemini 내부·HTTP 파이프라인 Smoke 기록

## 목적

실제 Gemini 호출로 내부 분석 파이프라인과 Backend Wire HTTP 경계를 단계적으로 검증한다.

```text
InternalPortfolioInput
→ 입력 참조·깊이 검증
→ 정규화
→ RepositoryAnalysis
→ PortfolioSynthesis
→ InterviewQuestion
→ PortfolioStatement
→ PortfolioAnalysis 조립
→ InternalPortfolioReport
```

## 실행 기준

```text
검증일: 2026-08-26
작업 브랜치: test/gemini-full-pipeline-smoke
모델: gemini-3.5-flash-lite
Thinking level: minimal
Provider retry: 0 (Smoke 중 무료 quota 보존)
Gemini 개별 호출 timeout: 180초
AI 전체 deadline: 600초
Repository: git-ddo/backend 1개
면접 질문: 1개
포트폴리오 문장: 1개
```

## 단계별 결과

| 실행 | 결과 | 생성 단계별 시간 | 시도 횟수 |
| --- | --- | --- | --- |
| 경량 Structured Output | 성공 | 7,232ms | 1 |
| RepositoryAnalysis P0 | 성공 | 4,329ms | 1 |
| 전체 P0 | 성공 | 4,426 + 3,359 + 2,581 + 2,125ms | 각 1 |
| 전체 P1 | 성공 | 4,420 + 3,483 + 2,666 + 2,063ms | 각 1 |
| 전체 P2 최초 | 실패 | Portfolio 정책 검증에서 중단 | Portfolio 1회 교정 후 실패 |
| 전체 P2 보완 후 | 성공 | 6,001 + 3,229 + 2,797 + 2,146ms | 각 1 |

시간 순서는 `Repository → Portfolio → Interview → Statement`이다. 실제 전체 P0/P1/P2 실행은
모두 600초 deadline 안에서 완료됐다.

## 확인된 실패 원인과 조치

### `gemini-3.6-flash` 무료 quota

경량 호출은 성공했지만 이어진 호출에서 HTTP 429가 발생했다.

```text
quota metric: generate_content_free_tier_requests
quota: GenerateRequestsPerDayPerProjectPerModel-FreeTier
limit: 20
```

이는 Prompt, JSON Schema 또는 timeout 문제가 아니라 해당 모델의 무료 요청 한도 소진이다.
Smoke에서는 quota가 분리된 `gemini-3.5-flash-lite`를 사용하고 불필요한 Provider retry를 끄고
검증했다.

### P2 `NOT_OBSERVED_MISUSE` 오탐

Gemini가 다음 의미의 올바른 한계를 생성했다.

```text
제공된 Evidence 범위 내에서만 분석했으며 snippet 밖은 직접 확인할 수 없다.
```

기존 Validator는 `없습니다`만 감지하고 `제공된 범위 내`, `snippet 밖`을 안전한 범위 표현으로
인식하지 못했다. `_OBSERVATION_SCOPE_PATTERNS`에 해당 표현을 좁게 추가하고 회귀 테스트를
작성했다. 실제 부재를 단정하는 문장은 계속 `NOT_OBSERVED_MISUSE`로 거절한다.

## 재현 명령

무료 quota를 불필요하게 소모하지 않도록 검증 중에는 retry를 0으로 둔다.

```bash
cd ai

GEMINI_MODEL=gemini-3.5-flash-lite \
GEMINI_THINKING_LEVEL=minimal \
LLM_TIMEOUT_SECONDS=180 \
LLM_MAX_RETRIES=0 \
AI_ANALYSIS_DEADLINE_SECONDS=600 \
PYTHONPATH=. .venv/bin/python scripts/smoke_internal_report.py \
  --repository-count 1 \
  --depth P2 \
  --question-count 1 \
  --statement-count 1
```

Runtime 결과 JSON은 `ai/scripts/*.output.json`에 생성되며 Git 추적에서 제외한다.

## Backend P1 Wire HTTP Smoke

Backend `origin/main`의 P1 request Example을 입력으로 다음 전체 HTTP 경계를 검증했다.

```text
Backend Request v1.0
→ POST /internal/v1/portfolio-reports
→ Request Wire Mapper
→ 실제 GeminiProvider와 Report Service
→ Response Wire Mapper
→ Backend Response v1.1
```

결과는 HTTP 200이며 `usedEvidenceLevels=[P0,P1]`, camelCase v1.1 Envelope, Finding·Coaching의
신뢰도와 참조 무결성을 확인했다. Portfolio 공개 강점에는 UserClaim을 사실처럼 참조하지 않고,
UserClaim은 계약상 `claimRefs`를 받을 수 있는 면접 질문·포트폴리오 문장에만 사용한다.

## Backend P2 Wire HTTP Smoke

실제 Backend `AiAnalysisRequestAssembler`가 생성한 합성 P2 Request로 전체 HTTP 경계를 검증했다.

```text
검증일: 2026-09-13
모델: gemini-3.5-flash-lite, thinking=minimal, Provider retry=0
HTTP: 200
completedEvidenceLevels: [P0, P1, P2]
실제 Evidence depth: [P0, P1, P1, P2]
usedEvidenceLevels: [P0, P1, P2]
```

Backend P2 Example과 AI Fixture에는 누락됐던 P0 README Evidence를 추가했다. 실제 Assembler
Request는 FastAPI Request Mapper·입력 Validator·Report Service·GeminiProvider·Response Mapper를
거쳐 Response v1.1을 반환했다. 응답은 AI Pydantic DTO와 Backend
`AiAnalysisResponseValidator`를 모두 통과했다.

## 현재 검증 기준

```text
pytest: 1201 passed
ruff check: passed
ruff format --check: passed
mypy app: passed
```

외부 SDK deprecation warning 2건 외 테스트 실패는 없다. Docker build는 이번 P2 HTTP Smoke에서
다시 실행하지 않았다.

## 아직 검증하지 않은 범위

- Repository 2~5개의 정식 전체 파이프라인
- 기본 질문 5개·문장 6개 출력
- 실제 Mapper·Validator·Report Service와 Fake LLMProvider를 연결한 HTTP 통합 테스트
- Spring Boot HTTP E2E
- P2 전역 snippet/token 예산과 수집 Warning 반영
- Backend Read Timeout 600초와 AI deadline 600초 사이의 운영 여유
