# AI 서버 개발 가이드

## 1. 목표

백엔드가 전달한 GitHub 근거 데이터와 사용자 입력을 바탕으로 구조화된 포트폴리오 코칭 리포트를 생성한다.

AI 서버는 다음 작업만 담당한다.

- 프로젝트별 분석
- 전체 포트폴리오 종합
- 대표 프로젝트 추천
- 직무별 보완 방향 생성
- GitHub 정리 로드맵 생성
- 면접 질문과 답변 가이드 생성
- 포트폴리오 문장 생성
- LLM 출력 검증

---

## 2. 아키텍처 경계

```text
[Spring Boot Backend]
GitHub API 호출
사용자·분석 상태 관리
README·파일·Commit·PR 수집
기술스택 근거 추출
규칙 기반 준비도 계산
사용자 역할 정보 관리
        ↓ JSON
[FastAPI AI Server]
입력 검증 및 정규화
직무·목적별 분석 기준 적용
프로젝트별 리포트 생성
전체 포트폴리오 종합
근거 및 출력 검증
        ↓ JSON
[Spring Boot Backend]
결과 저장 및 조회
        ↓
[React Frontend]
리포트 시각화
```

### AI 서버가 하지 않는 일

- GitHub OAuth 처리
- GitHub API 직접 호출
- 사용자 및 세션 관리
- 분석 상태 DB 관리
- 원본 Repository 전체 저장
- 개인 기여율 계산
- Commit 수를 실력 점수로 변환
- GitHub에서 확인되지 않은 기술 추정
- Private Repository 권한 관리

---

## 3. 기술 스택

### 필수 기술

| 영역 | 기술 | 용도 |
|---|---|---|
| Language | Python 3.12+ | AI 서버 개발 |
| API | FastAPI | 백엔드 연동 API |
| Server | Uvicorn | ASGI 서버 |
| Schema | Pydantic v2 | 요청·응답 검증 |
| Settings | pydantic-settings | 환경변수 관리 |
| LLM | Google Gen AI SDK (`google-genai`) | Gemini API 호출 |
| Output | Gemini Structured Output | JSON Schema 기반 출력 |
| HTTP | httpx | 외부 HTTP 통신 |
| Retry | tenacity | 제한적인 LLM 재시도 |
| Criteria | PyYAML | 직무별 평가 기준 관리 |
| Test | pytest | 단위·통합 테스트 |
| Async Test | pytest-asyncio | 비동기 테스트 |
| Lint/Format | Ruff | 코드 품질 관리 |
| Type Check | mypy 또는 pyright | 정적 타입 검사 |
| Infra | Docker | 실행 환경 표준화 |
| CI | GitHub Actions | 테스트·검사 자동화 |

### MVP에서 사용하지 않는 기술

- LangChain
- RAG
- Vector Database
- Fine-tuning
- 자체 ML 모델
- AI Agent
- Redis
- AI 서버의 GitHub API 연동

---

## 4. 권장 디렉터리 구조

```text
ai/
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── health.py
│   │   └── reports.py
│   ├── core/
│   │   ├── config.py
│   │   ├── exceptions.py
│   │   └── logging.py
│   ├── schemas/
│   │   ├── common.py
│   │   ├── request.py
│   │   ├── response.py
│   │   └── repository.py
│   ├── criteria/
│   │   ├── backend.yaml
│   │   ├── frontend.yaml
│   │   ├── ai.yaml
│   │   └── cloud_infra.yaml
│   ├── prompts/
│   │   ├── system.py
│   │   ├── repository.py
│   │   ├── portfolio.py
│   │   └── interview.py
│   ├── llm/
│   │   ├── provider.py
│   │   └── gemini_provider.py
│   ├── services/
│   │   ├── normalization_service.py
│   │   ├── repository_service.py
│   │   ├── portfolio_service.py
│   │   └── report_service.py
│   └── validators/
│       ├── evidence_validator.py
│       └── report_validator.py
├── tests/
│   ├── fixtures/
│   ├── test_api.py
│   ├── test_normalization.py
│   ├── test_prompt_routing.py
│   └── test_evidence_validator.py
├── .env.example
├── Dockerfile
├── pyproject.toml
└── README.md
```

---

## 5. API

### Health Check

```http
GET /health
```

```json
{
  "status": "UP"
}
```

### 포트폴리오 리포트 생성

```http
POST /ai/v1/portfolio-reports
Content-Type: application/json
```

처음에는 동기 HTTP API로 구현한다. 분석 Job과 상태 관리는 Spring Boot가 담당한다.

---

## 6. 공통 Enum

백엔드와 AI 서버가 동일한 값을 사용해야 한다.

```text
TargetJob
- BACKEND
- FRONTEND
- AI
- CLOUD_INFRA

AnalysisPurpose
- GITHUB_DIAGNOSIS
- PORTFOLIO_ORGANIZATION
- JOB_PREPARATION
- INTERVIEW_PREPARATION

ProjectType
- PERSONAL
- TEAM

EvidenceType
- GITHUB
- USER_PROVIDED
- BACKEND_DERIVED
- AI_RECOMMENDATION

Confidence
- HIGH
- MEDIUM
- LOW

Priority
- HIGH
- MEDIUM
- LOW
```

---

## 7. 요청 스키마 책임

### 백엔드 책임

백엔드는 AI 서버에 원본 Repository 전체가 아니라 구조화된 근거를 전달한다.

- `analysisId` 생성
- 희망 직무와 분석 목적 검증
- Repository 개수 검증
- README 분석 결과 생성
- 기술스택 후보와 근거 생성
- 테스트·Docker·CI 존재 여부 계산
- 제한된 Commit·PR 활동 데이터 생성
- 사용자 입력 역할을 별도 필드로 전달
- 정량적인 준비도 점수 계산
- 파일 경로와 기술 이름 정규화
- 입력 크기 제한

### AI 서버 책임

- Pydantic 요청 검증
- Enum 및 필수 필드 검증
- 데이터 추가 정규화
- 직무별 분석 기준 선택
- 분석 목적별 출력 강조점 선택
- GitHub 근거와 사용자 입력 분리 유지
- 프로젝트별 분석 생성
- 전체 포트폴리오 종합
- 응답 JSON Schema 검증
- 근거 없는 문장 제거 또는 실패 처리

---

## 8. 요청 JSON 예시

```json
{
  "schemaVersion": "1.0",
  "analysisId": 123,
  "targetJob": "BACKEND",
  "analysisPurpose": "INTERVIEW_PREPARATION",
  "repositories": [
    {
      "repositoryId": 1001,
      "name": "festival-order-service",
      "fullName": "kang-dev/festival-order-service",
      "description": "축제 부스 주문 관리 서비스",
      "githubEvidence": {
        "languages": [
          {
            "name": "Java",
            "percentage": 88.5
          }
        ],
        "techStacks": [
          {
            "name": "Spring Boot",
            "confidence": "HIGH",
            "evidence": [
              {
                "type": "GITHUB",
                "path": "build.gradle",
                "description": "Spring Boot 플러그인과 의존성이 확인됨"
              }
            ]
          }
        ],
        "readme": {
          "exists": true,
          "hasIntroduction": true,
          "hasFeatures": true,
          "hasRunGuide": false,
          "hasEnvironmentVariables": false,
          "hasTechStack": true,
          "hasApiExamples": false,
          "hasTestingGuide": false,
          "hasDeploymentGuide": false,
          "hasTroubleshooting": false
        },
        "testing": {
          "exists": true,
          "fileCount": 4
        },
        "docker": {
          "dockerfile": true,
          "compose": false
        },
        "ci": {
          "githubActions": false,
          "runsBuild": false,
          "runsTests": false
        },
        "activity": {
          "recentCommitCount": 12,
          "userCommitCount": 7,
          "userPullRequestCount": 2,
          "activityAreaCandidates": [
            "CONTROLLER",
            "SERVICE",
            "SECURITY"
          ]
        }
      },
      "backendMetrics": {
        "portfolioReadinessScore": 68,
        "readmeReadinessScore": 45,
        "evidenceClarityScore": 80
      },
      "userProvidedRole": {
        "projectType": "TEAM",
        "role": "Backend",
        "implementedFeatures": [
          "주문 생성 API",
          "운영자 주문 상태 변경 API"
        ],
        "relatedFiles": [
          "src/main/java/example/order/OrderController.java",
          "src/main/java/example/order/OrderService.java"
        ],
        "relatedPullRequests": [],
        "relatedCommits": []
      }
    }
  ]
}
```

### 요청 데이터 원칙

```text
githubEvidence
→ GitHub에서 확인된 사실

backendMetrics
→ 백엔드 규칙으로 계산된 결과

userProvidedRole
→ 사용자가 직접 입력한 주장
```

세 종류의 데이터를 하나의 사실처럼 합치지 않는다.

---

## 9. 응답 스키마 책임

AI 서버는 자유 형식 Markdown이 아닌 구조화된 JSON을 반환한다.

각 핵심 판단은 가능하면 다음 정보를 포함한다.

- 내용
- 근거 유형
- 근거
- 신뢰도
- 실행 가능한 제안

AI 서버는 점수를 새로 임의 생성하지 않는다. 백엔드가 계산한 준비도 지표를 설명하고 보완 방향을 생성한다.

---

## 10. 응답 JSON 예시

```json
{
  "schemaVersion": "1.0",
  "analysisId": 123,
  "overallDiagnosis": {
    "summary": "백엔드 프로젝트의 도메인과 사용 기술은 확인되지만 문서화와 자동화 경험이 충분히 드러나지 않습니다.",
    "strengths": [
      {
        "content": "Spring Boot 기반 주문 도메인 구현 경험이 드러납니다.",
        "evidenceType": "GITHUB",
        "evidence": [
          "build.gradle",
          "src/main/java/example/order/OrderController.java"
        ],
        "confidence": "HIGH"
      }
    ],
    "improvements": [
      {
        "content": "README에 실행 방법과 API 호출 예시를 추가해야 합니다.",
        "evidenceType": "BACKEND_DERIVED",
        "evidence": [
          "README 실행 방법 없음",
          "README API 예시 없음"
        ],
        "confidence": "HIGH"
      }
    ]
  },
  "representativeProjects": [
    {
      "repositoryName": "festival-order-service",
      "reason": "도메인과 담당 기능이 구체적이고 백엔드 직무와의 연관성이 높습니다.",
      "evidenceType": "USER_PROVIDED",
      "evidence": [
        "주문 생성 API",
        "운영자 주문 상태 변경 API"
      ]
    }
  ],
  "repositoryReports": [
    {
      "repositoryName": "festival-order-service",
      "summary": "주문 관리 도메인을 중심으로 구성된 Spring Boot 프로젝트입니다.",
      "strengths": [],
      "improvements": [],
      "interviewPoints": []
    }
  ],
  "jobAppeal": {
    "targetJob": "BACKEND",
    "visibleExperiences": [
      "Spring Boot 기반 API 구현",
      "주문 도메인 비즈니스 로직 구현"
    ],
    "experiencesToHighlight": [
      "도메인 규칙을 Service 계층에서 처리한 이유"
    ],
    "experiencesToImprove": [
      "테스트 자동화",
      "CI 구성",
      "README 실행 가이드"
    ]
  },
  "roadmap": [
    {
      "priority": "HIGH",
      "title": "README 실행 가이드 작성",
      "reason": "현재 실행 방법과 환경변수 설명이 확인되지 않습니다.",
      "actions": [
        "필수 환경변수 목록 작성",
        "로컬 실행 명령 추가",
        "API 요청 예시 추가"
      ],
      "expectedEffect": "프로젝트 재현 가능성과 설명력이 높아집니다."
    }
  ],
  "interviewQuestions": [
    {
      "repositoryName": "festival-order-service",
      "question": "주문 상태 변경 규칙을 Service 계층에서 처리한 이유는 무엇인가요?",
      "intent": "비즈니스 로직 분리와 계층별 책임에 대한 이해를 확인하기 위한 질문입니다.",
      "answerGuide": [
        "Controller와 Service의 책임 차이",
        "상태 변경 규칙의 재사용성",
        "단위 테스트 용이성"
      ],
      "followUpQuestions": [
        "동시에 상태 변경 요청이 발생하면 어떻게 처리할 수 있나요?"
      ],
      "evidenceType": "USER_PROVIDED",
      "evidence": [
        "운영자 주문 상태 변경 API",
        "OrderService.java"
      ]
    }
  ],
  "portfolioStatements": {
    "resume": "Spring Boot 기반 주문 관리 API와 운영자 주문 상태 변경 기능을 구현했습니다.",
    "portfolio": "Spring Boot 기반 축제 주문 관리 서비스에서 주문 생성 API와 운영자 주문 상태 변경 기능을 담당했습니다.",
    "interview": "주문 상태 변경 규칙을 Service 계층에 배치하여 HTTP 요청 처리와 비즈니스 규칙의 책임을 분리했습니다."
  },
  "limitations": [
    "공개 GitHub 데이터와 사용자 입력만을 기준으로 생성된 결과입니다.",
    "Commit 수만으로 실제 개인 기여도를 판단하지 않았습니다.",
    "사용자 입력 역할은 GitHub에서 확인된 사실과 구분됩니다."
  ]
}
```

---

## 11. AI 처리 파이프라인

```text
1. 요청 수신
2. Pydantic 스키마 검증
3. 입력 정규화
4. 직무별 Criteria 선택
5. 분석 목적별 Prompt 선택
6. Repository별 분석
7. 전체 Portfolio 종합
8. Structured Output 변환
9. Evidence 검증
10. Pydantic 응답 검증
11. 백엔드에 JSON 반환
```

### Repository별 분석

각 Repository를 독립적으로 분석한다.

```text
Repository A → RepositoryReport A
Repository B → RepositoryReport B
Repository C → RepositoryReport C
```

분석 항목:

- 프로젝트 요약
- 확인된 강점
- 부족하게 드러나는 부분
- README 보완 방향
- 직무 관련 어필 포인트
- 면접 소재

### 전체 Portfolio 종합

Repository별 결과를 바탕으로 다음을 생성한다.

- 전체 진단
- 대표 프로젝트 추천
- 프로젝트 간 중복성과 차별성
- 희망 직무 기준 어필 요소
- 보완할 경험
- 개선 로드맵
- 면접 질문
- 포트폴리오 문장

---

## 12. 직무별 Criteria

직무별 기준은 YAML로 관리한다.

### Backend

```yaml
target_job: BACKEND
criteria:
  - domain_and_api_design
  - database_and_orm
  - authentication_and_authorization
  - exception_handling
  - testing
  - docker_and_deployment
  - ci_cd
  - operations
  - documentation
```

### Frontend

```yaml
target_job: FRONTEND
criteria:
  - component_structure
  - typescript
  - state_management
  - api_integration
  - routing
  - loading_error_empty_states
  - accessibility
  - responsive_design
  - testing
  - build_and_deployment
```

### AI

```yaml
target_job: AI
criteria:
  - problem_definition
  - data_processing
  - model_or_llm_selection
  - training_or_inference_pipeline
  - evaluation_metrics
  - experiment_tracking
  - hallucination_control
  - reproducibility
  - cost_and_latency
  - service_integration
```

### Cloud/Infra

```yaml
target_job: CLOUD_INFRA
criteria:
  - docker
  - ci_cd
  - cloud_deployment
  - network
  - secrets_management
  - logging
  - monitoring
  - failure_recovery
  - automation
  - scalability
```

---

## 13. 분석 목적별 Prompt Routing

| 목적 | 강조할 결과 |
|---|---|
| `GITHUB_DIAGNOSIS` | README, 문서화, 테스트, Docker, CI/CD, Repository 정리 상태 |
| `PORTFOLIO_ORGANIZATION` | 대표 프로젝트, 프로젝트 순서, 포트폴리오 문장, README 보완 |
| `JOB_PREPARATION` | 직무 관련 경험, 부족하게 드러나는 경험, 개선 로드맵 |
| `INTERVIEW_PREPARATION` | 예상 질문, 질문 의도, 답변 가이드, 꼬리질문, 강조 포인트 |

Prompt는 다음 조합으로 선택한다.

```text
TargetJob × AnalysisPurpose
```

예시:

```text
BACKEND × INTERVIEW_PREPARATION
AI × PORTFOLIO_ORGANIZATION
```

---

## 14. 근거 기반 생성 규칙

모든 Prompt와 검증 코드에서 다음 규칙을 적용한다.

- 입력에 없는 기술을 사용했다고 말하지 않는다.
- 입력에 없는 파일 경로를 근거로 생성하지 않는다.
- 파일 존재를 사용자의 숙련도로 해석하지 않는다.
- Commit 수를 개인 기여도나 실력으로 해석하지 않는다.
- 사용자 역할 입력은 사용자 진술로 표시한다.
- GitHub 근거와 사용자 입력을 혼합하지 않는다.
- 직무 적합도를 취업 가능성으로 표현하지 않는다.
- 점수는 역량 점수가 아닌 포트폴리오 준비도로 표현한다.
- 불확실한 판단에는 `LOW` confidence 또는 확인 필요를 표시한다.
- 공개 GitHub 데이터 기준이라는 한계를 응답에 포함한다.

---

## 15. 출력 검증

LLM 응답을 백엔드로 바로 반환하지 않는다.

### 검증 항목

- 언급한 기술이 입력 `techStacks`에 존재하는가
- 언급한 파일이 입력 근거에 존재하는가
- Repository 이름이 요청 목록에 존재하는가
- GitHub 근거와 사용자 입력 근거를 올바르게 구분했는가
- Commit 수를 기여도라고 표현하지 않았는가
- 사용자의 실력이나 취업 가능성을 단정하지 않았는가
- 필수 응답 필드가 존재하는가
- Enum 값이 유효한가
- Repository별 결과가 중복되지 않았는가

### 검증 실패 처리

```text
수정 가능한 오류
→ 잘못된 항목 제거 또는 정규화

JSON Schema 오류
→ 제한 횟수 내 재생성

근거 없는 핵심 주장
→ 해당 주장 제거

복구 불가능한 응답
→ 명시적인 오류 반환
```

무한 재시도는 허용하지 않는다.

---

## 16. 구현 단계

### Phase 1. 프로젝트 기반 구성

- [x] Python 3.12 환경 구성
- [x] FastAPI 프로젝트 생성
- [x] `/health` API 구현
- [x] 환경변수 설정
- [x] Ruff 설정
- [x] 타입 검사 설정
- [x] pytest 설정
- [x] Dockerfile 작성
- [x] GitHub Actions 기본 검사 구성

완료 조건:

```text
서버 실행 가능
/health 응답 성공
lint와 테스트 통과
Docker 실행 성공
```

---

### Phase 2. API 계약 확정

- [ ] 백엔드 팀과 Request JSON 확정
- [ ] 백엔드 팀과 Response JSON 확정
- [x] 공통 Enum 확정
- [x] `schemaVersion` 정책 확정
- [x] Pydantic Request 모델 작성
- [x] Pydantic Response 모델 작성
- [x] 정상·경계·실패 예시 JSON 작성
- [ ] OpenAPI 문서 확인

완료 조건:

```text
Mock 요청을 검증할 수 있음
Mock 응답을 검증할 수 있음
백엔드가 동일한 계약으로 DTO를 작성할 수 있음
```

---

### Phase 3. Mock 리포트 API

- [ ] `POST /ai/v1/portfolio-reports` 구현
- [ ] Mock 요청 Fixture 작성
- [ ] 고정된 Mock 응답 반환
- [ ] Repository 1개와 5개 입력 테스트
- [ ] 잘못된 Enum 테스트
- [ ] 필수 필드 누락 테스트
- [ ] Repository 개수 제한 테스트

완료 조건:

```text
Spring Boot와 LLM 없이 API 연동 가능
요청·응답 스키마 오류를 명확하게 반환
```

---

### Phase 4. 직무·목적별 기준 구성

- [ ] Backend Criteria 작성
- [ ] Frontend Criteria 작성
- [ ] AI Criteria 작성
- [ ] Cloud/Infra Criteria 작성
- [ ] 분석 목적별 강조 항목 작성
- [ ] Criteria Loader 구현
- [ ] Prompt Router 구현
- [ ] 모든 직무·목적 조합 테스트

완료 조건:

```text
TargetJob과 AnalysisPurpose에 따라
적절한 Criteria와 Prompt를 선택할 수 있음
```

---

### Phase 5. LLM Provider 연동

- [ ] 공통 `LLMProvider` 인터페이스 정의
- [ ] Google Gen AI SDK 기반 Gemini Provider 구현
- [ ] Timeout 설정
- [ ] 제한적인 Retry 설정
- [ ] Gemini Structured Output과 Pydantic 응답 모델 연결
- [ ] 모델명 환경변수화
- [ ] API 오류 변환
- [ ] 사용량 및 처리 시간 로그 기록

완료 조건:

```text
Mock 입력을 LLM에 전달하고
Response Schema에 맞는 JSON을 받을 수 있음
```

---

### Phase 6. Repository별 분석

- [ ] Repository 분석 Prompt 작성
- [ ] GitHub 근거와 사용자 입력 분리
- [ ] 프로젝트 요약 생성
- [ ] 강점 생성
- [ ] 보완점 생성
- [ ] 직무별 어필 포인트 생성
- [ ] 면접 소재 생성
- [ ] Repository별 결과 Schema 검증
- [ ] 근거가 부족한 Repository 테스트

완료 조건:

```text
각 Repository가 독립된 구조화 결과를 반환
모든 핵심 판단에 근거 유형이 포함됨
```

---

### Phase 7. 전체 Portfolio 종합

- [ ] Repository별 결과 수집
- [ ] 전체 진단 생성
- [ ] 대표 프로젝트 추천
- [ ] 직무별 어필 요소 생성
- [ ] 부족하게 드러나는 경험 생성
- [ ] 개선 로드맵 생성
- [ ] 포트폴리오 문장 생성
- [ ] 면접 질문과 답변 가이드 생성
- [ ] 분석 한계 문구 생성

완료 조건:

```text
1~5개 Repository 결과를 종합한
PortfolioReport JSON 반환
```

---

### Phase 8. Evidence 검증

- [ ] 허용된 기술 목록 생성
- [ ] 허용된 파일 경로 목록 생성
- [ ] 허용된 Repository 이름 목록 생성
- [ ] 근거 없는 기술 검출
- [ ] 존재하지 않는 파일 근거 검출
- [ ] 근거 유형 혼동 검출
- [ ] 기여도 단정 표현 검출
- [ ] 역량·취업 가능성 단정 표현 검출
- [ ] 검증 실패 정책 구현

완료 조건:

```text
입력에 없는 기술과 파일을
최종 응답에 포함하지 않음
```

---

### Phase 9. 테스트

- [ ] Spring Boot Repository Fixture
- [ ] React Repository Fixture
- [ ] AI/FastAPI Repository Fixture
- [ ] Cloud/Infra Repository Fixture
- [ ] README가 없는 입력
- [ ] Commit과 PR이 없는 입력
- [ ] 팀 프로젝트 역할이 없는 입력
- [ ] 사용자 역할만 있고 GitHub 근거가 없는 입력
- [ ] Repository 1개 입력
- [ ] Repository 5개 입력
- [ ] 지나치게 긴 입력
- [ ] LLM Timeout
- [ ] Rate Limit
- [ ] 잘못된 JSON
- [ ] 근거 없는 기술 생성
- [ ] 동일 입력 반복 결과 비교

완료 조건:

```text
API, Schema, Router, Validator 테스트 통과
주요 Hallucination 사례 차단
```

---

### Phase 10. Spring Boot 통합

- [ ] 백엔드 개발 환경에서 API 호출
- [ ] 인증 방식 또는 내부 네트워크 정책 확정
- [ ] Timeout 합의
- [ ] Retry 담당 주체 합의
- [ ] 오류 코드 매핑
- [ ] 실제 분석 데이터로 테스트
- [ ] 요청 크기 제한 적용
- [ ] 로그에서 민감 데이터 제거
- [ ] Prompt 및 모델 버전 전달 또는 저장 방식 확정

완료 조건:

```text
Spring Boot 요청
→ AI 분석
→ JSON 응답 검증
→ DB 저장
과정이 정상 동작
```

---

## 17. 테스트 우선순위

### 필수

- 요청·응답 Schema
- Prompt Routing
- Evidence Validation
- LLM Timeout
- 잘못된 JSON 처리
- 존재하지 않는 기술·파일 생성 방지
- GitHub 근거와 사용자 입력 구분

### 품질 평가

- 희망 직무에 맞는 결과인가
- 분석 목적에 따라 결과가 달라지는가
- 대표 프로젝트 추천 이유가 구체적인가
- 개선 행동이 실행 가능한가
- 면접 질문이 실제 프로젝트 근거와 연결되는가
- 포트폴리오 문장을 바로 활용할 수 있는가
- 사용자의 실력이나 기여도를 과장하지 않는가

---

## 18. 환경변수

```env
APP_ENV=local
APP_HOST=0.0.0.0
APP_PORT=8000

LLM_PROVIDER=gemini
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.6-flash
LLM_TIMEOUT_SECONDS=60
LLM_MAX_RETRIES=2

MAX_REPOSITORIES=5
MAX_REQUEST_BYTES=
LOG_LEVEL=INFO
```

실제 비밀값은 Repository에 커밋하지 않는다.

---

## 19. MVP 완료 기준

- [ ] FastAPI 서버가 Docker에서 실행된다.
- [ ] 백엔드 요청 Schema를 검증한다.
- [ ] 최대 5개 Repository를 처리한다.
- [ ] 네 가지 희망 직무를 지원한다.
- [ ] 네 가지 분석 목적을 지원한다.
- [ ] Repository별 분석을 생성한다.
- [ ] 전체 포트폴리오 리포트를 생성한다.
- [ ] 대표 프로젝트와 추천 이유를 반환한다.
- [ ] 개선 로드맵을 반환한다.
- [ ] 면접 질문과 답변 가이드를 반환한다.
- [ ] 포트폴리오 문장을 반환한다.
- [ ] 모든 결과를 구조화된 JSON으로 반환한다.
- [ ] GitHub 근거와 사용자 입력을 구분한다.
- [ ] 입력에 없는 기술과 파일을 검출한다.
- [ ] LLM 오류와 Timeout을 명확하게 반환한다.
- [ ] 핵심 테스트와 CI 검사가 통과한다.
