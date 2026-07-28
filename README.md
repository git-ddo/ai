# 프로젝트 이름

> GitHub 프로젝트를 취업 경쟁력으로 바꾸는 AI 포트폴리오 코칭 서비스

개발자 취업을 준비하는 사용자가 자신의 GitHub 프로젝트를 포트폴리오 관점에서 점검하고 정리할 수 있도록 돕는 웹 서비스입니다.

사용자가 GitHub 계정으로 로그인한 뒤 분석할 public repository를 선택하고, 희망 직무와 프로젝트 역할을 입력하면 GitHub에서 확인 가능한 근거와 사용자 입력 정보를 바탕으로 포트폴리오 코칭 리포트를 제공합니다.

---

## 프로젝트 소개

개발자 취업 준비 과정에서 GitHub는 프로젝트 경험과 개발 역량을 보여주는 중요한 포트폴리오 수단으로 활용됩니다.

하지만 많은 학생과 취업 준비생은 프로젝트를 GitHub에 올려두고도 다음과 같은 어려움을 겪습니다.

- 어떤 repository를 대표 프로젝트로 선택해야 하는지 알기 어렵습니다.
- README에 어떤 내용을 추가해야 하는지 판단하기 어렵습니다.
- 사용한 기술을 포트폴리오에서 어떻게 설명해야 하는지 알기 어렵습니다.
- 팀 프로젝트에서 자신의 역할과 구현 내용을 정리하기 어렵습니다.
- 면접에서 어떤 프로젝트와 기술적 경험을 강조해야 하는지 알기 어렵습니다.
- 희망 직무에 맞추어 어떤 경험을 보완해야 하는지 판단하기 어렵습니다.

이 서비스는 공개 GitHub repository에서 확인할 수 있는 정보와 사용자가 직접 입력한 프로젝트 역할을 함께 활용하여 다음 내용을 제공합니다.

- 대표 프로젝트 추천
- 프로젝트별 포트폴리오 준비도 분석
- 기술스택과 근거 파일 정리
- README 보완 방향
- 희망 직무 기준 보완점
- GitHub 정리 로드맵
- 예상 면접 질문과 답변 가이드
- 이력서 및 포트폴리오용 프로젝트 문장

---

## 핵심 원칙

이 서비스는 GitHub 기록만으로 사용자의 실력이나 팀 프로젝트 기여도를 확정하지 않습니다.

분석 결과는 다음 세 가지 정보를 구분하여 사용합니다.

1. **GitHub에서 확인된 근거**
   - README
   - 기술스택 관련 설정 파일
   - 파일 구조
   - 테스트 코드
   - Docker 및 CI/CD 구성
   - 제한적으로 수집한 commit과 PR 정보

2. **사용자가 직접 입력한 정보**
   - 개인 프로젝트 또는 팀 프로젝트 여부
   - 담당 파트
   - 직접 구현한 기능
   - 관련 파일
   - 관련 PR 또는 commit

3. **AI가 생성한 제안**
   - 포트폴리오 보완 방향
   - 대표 프로젝트 추천
   - 면접 질문
   - 포트폴리오 문장
   - 향후 개선 로드맵

GitHub에서 확인되지 않은 기술은 사용했다고 단정하지 않으며, commit 수를 개인 기여도나 개발 실력으로 직접 해석하지 않습니다.

---

## MVP 사용자 흐름

```text
GitHub OAuth 로그인
        ↓
사용자 public repository 목록 조회
        ↓
분석할 repository 최대 3~5개 선택
        ↓
희망 직무와 분석 목적 선택
        ↓
프로젝트별 개인/팀 프로젝트 여부 입력
        ↓
팀 프로젝트 담당 역할과 구현 기능 입력
        ↓
GitHub repository 데이터 수집
        ↓
백엔드 1차 근거 데이터 계산
        ↓
AI 포트폴리오 코칭 리포트 생성
        ↓
분석 결과 저장
        ↓
리포트 및 이전 분석 기록 조회
```

---

## 주요 기능

### 1. GitHub OAuth 로그인

별도의 회원가입 없이 GitHub 계정으로 서비스를 시작할 수 있습니다.

로그인 후 다음 사용자 정보를 조회하여 서비스 사용자와 연결합니다.

- GitHub ID
- GitHub 로그인 아이디
- 이름
- 프로필 이미지
- 이메일 주소(공개 또는 권한이 허용된 경우)

---

### 2. Public repository 조회 및 선택

로그인한 사용자의 public repository 목록을 GitHub REST API로 불러옵니다.

repository 카드에는 다음 정보를 표시합니다.

- repository 이름
- 설명
- 주 사용 언어
- 최근 업데이트 날짜
- star 수
- fork 여부
- archived 여부
- README 존재 여부

사용자는 포트폴리오 분석에 사용할 repository를 최대 3~5개까지 선택할 수 있습니다.

---

### 3. 분석 조건 설정

사용자는 분석 결과를 개인화하기 위해 희망 직무와 분석 목적을 선택합니다.

#### 희망 직무

- 백엔드 개발자
- 프론트엔드 개발자
- AI 개발자
- 클라우드·인프라 개발자

#### 분석 목적

- 현재 GitHub 상태 진단
- 포트폴리오 정리 방향 확인
- 취업 직무에 맞는 보완 방향 확인
- 면접 대비

---

### 4. 프로젝트 역할 입력

각 repository가 개인 프로젝트인지 팀 프로젝트인지 선택합니다.

팀 프로젝트인 경우 다음 정보를 추가로 입력할 수 있습니다.

- 담당 파트
- 직접 구현한 기능
- 관련 파일 경로
- 관련 PR 링크
- 관련 commit 링크
- 프로젝트에서 해결한 문제

사용자 입력 역할은 GitHub에서 자동으로 확인된 사실과 구분하여 리포트에 반영합니다.

---

### 5. Repository 근거 데이터 분석

선택된 repository에서 다음 데이터를 제한적으로 수집하고 분석합니다.

#### 문서 및 구조

- README
- 파일 트리
- repository 설명
- 사용 언어

#### 기술스택 근거 파일

- `build.gradle`
- `pom.xml`
- `package.json`
- `requirements.txt`
- `pyproject.toml`
- `Dockerfile`
- `docker-compose.yml`
- `.github/workflows/*`

#### 품질 및 운영 구성

- 테스트 코드 존재 여부
- Docker 구성 여부
- GitHub Actions 구성 여부
- 최근 업데이트 여부

#### GitHub 활동 참고 지표

- 최근 commit 일부
- 로그인 사용자가 작성한 commit 일부
- 최근 PR 일부
- 사용자가 작성한 PR 일부
- PR 변경 파일 일부

commit과 PR 데이터는 개인 기여도를 확정하는 용도가 아니라 GitHub에서 확인되는 활동을 보조적으로 설명하는 데 사용합니다.

---

### 6. 백엔드 기반 1차 근거 계산

AI에 repository 원본 전체를 그대로 전달하지 않고, 백엔드에서 먼저 핵심 근거를 구조화합니다.

예시는 다음과 같습니다.

- README 준비도
- 기술스택 후보와 근거 파일
- 테스트 코드 존재 여부
- Docker 구성 여부
- GitHub Actions 구성 여부
- 최근 GitHub 활동 참고 지표
- 변경 파일 기반 활동 영역 후보
- 사용자 역할 정보

활동 영역은 다음과 같은 후보로 분류할 수 있습니다.

- Controller
- Service
- Repository
- Entity
- Security
- Config
- Test
- Frontend UI
- State Management
- AI/Model
- Data Processing
- CI/CD
- Docker
- Infrastructure

---

### 7. AI 포트폴리오 코칭 리포트

백엔드가 구조화한 GitHub 근거와 사용자 역할 정보를 AI 서버에 전달하여 리포트를 생성합니다.

리포트에는 다음 내용이 포함됩니다.

#### 전체 포트폴리오 진단

선택된 프로젝트들이 희망 직무를 얼마나 효과적으로 보여주고 있는지 분석합니다.

#### 대표 프로젝트 추천

포트폴리오와 면접에서 우선적으로 강조할 프로젝트와 추천 이유를 제공합니다.

#### 프로젝트별 분석

각 프로젝트의 강점, 부족한 점, README 및 기술 설명 보완 방향을 제공합니다.

#### 직무별 어필 포인트

희망 직무를 기준으로 현재 드러나는 경험과 추가로 보완하면 좋은 경험을 정리합니다.

#### GitHub 정리 로드맵

README, 테스트, 배포, CI/CD, 기술 선택 이유 등을 어떤 순서로 보완할지 제안합니다.

#### 예상 면접 질문

프로젝트와 실제 근거를 기반으로 질문, 질문 의도, 답변 가이드와 꼬리질문 후보를 생성합니다.

#### 포트폴리오 문장

사용자의 역할과 구현 기능을 바탕으로 다음 형식의 문장을 제공합니다.

- 이력서용 짧은 문장
- 포트폴리오용 상세 설명
- 면접 답변용 설명

---

### 8. 분석 상태 확인

GitHub 데이터 수집과 AI 리포트 생성에는 시간이 소요될 수 있으므로 분석을 비동기적으로 처리합니다.

분석 상태는 다음과 같이 관리합니다.

```text
PENDING
FETCHING_REPOSITORIES
ANALYZING_REPOSITORIES
CALCULATING_EVIDENCE
REQUESTING_AI
COMPLETED
FAILED
```

프론트엔드는 `analysisId`를 기반으로 분석 상태를 주기적으로 조회하고 현재 진행 단계를 사용자에게 표시합니다.

---

### 9. 리포트 저장 및 마이페이지

생성된 분석 결과는 사용자 계정과 연결하여 데이터베이스에 저장합니다.

사용자는 마이페이지에서 다음 정보를 확인할 수 있습니다.

- 이전 분석 기록
- 분석 날짜
- 선택한 희망 직무
- 분석 목적
- 분석한 repository
- 리포트 요약
- 이전 리포트 다시 보기

이를 통해 GitHub를 보완한 뒤 다시 분석하고 이전 결과와 비교할 수 있는 기반을 마련합니다.

---

## 화면 구성

MVP는 다음 화면으로 구성합니다.

1. 랜딩 페이지
2. GitHub 로그인 화면
3. 홈 대시보드
4. Repository 선택 화면
5. 분석 조건 설정 화면
6. 프로젝트 역할 입력 화면
7. 분석 진행 화면
8. AI 포트폴리오 리포트
9. 프로젝트별 상세 분석 화면
10. 마이페이지

UI는 GitHub와 Linear의 개발자 도구 스타일을 참고하여 카드 기반 대시보드 형태로 구성합니다.

---

## 시스템 아키텍처

```text
[React Frontend]
- GitHub 로그인 진입
- Repository 선택
- 분석 조건 및 프로젝트 역할 입력
- 분석 상태 조회
- AI 리포트 표시
- 마이페이지

        ↓ REST API

[Spring Boot Backend]
- GitHub OAuth 인증
- 사용자 및 세션 관리
- GitHub REST API 연동
- Repository 데이터 수집
- 1차 근거 데이터 계산
- 분석 요청 및 상태 관리
- AI 서버 호출
- 분석 결과 저장

        ↓ HTTP API

[FastAPI AI Server]
- 직무별 분석 기준 적용
- 분석 목적별 프롬프트 선택
- 대표 프로젝트 추천
- 프로젝트별 보완 방향 생성
- GitHub 정리 로드맵 생성
- 면접 질문 및 포트폴리오 문장 생성

        ↓

[PostgreSQL]
- 사용자 정보
- 분석 요청
- Repository별 분석 정보
- 사용자 역할 입력
- AI 리포트
- 면접 질문
- 개선 로드맵
```

---

## 기술 스택

### Frontend

- React
- TypeScript
- Vite
- React Router
- TanStack Query
- Tailwind CSS

### Backend

- Java 21
- Spring Boot
- Spring Security
- Spring OAuth2 Client
- Spring Data JPA
- WebClient
- PostgreSQL

### AI

- Python
- FastAPI
- Pydantic
- LLM API
- 직무별 프롬프트 템플릿
- 구조화된 JSON 응답

### Infrastructure

- Docker
- Docker Compose
- GitHub Actions
- AWS EC2/RDS 확장 고려
- Redis 확장 고려

---

## 담당 역할

### Frontend

- React 프로젝트와 라우팅 구조 구성
- GitHub 로그인 및 홈 대시보드 UI
- Repository 선택 화면
- 희망 직무 및 분석 목적 선택 화면
- 프로젝트 역할 입력 화면
- 분석 상태 polling 및 진행 화면
- AI 리포트 시각화
- 마이페이지
- 로딩, 오류, 빈 데이터 상태 처리
- 반응형 UI 구현

### Backend

- Spring Boot 프로젝트 및 PostgreSQL 환경 구성
- GitHub OAuth 로그인과 세션 인증
- 사용자 및 분석 관련 도메인 설계
- GitHub REST API 데이터 수집
- 분석 요청과 상태 관리
- repository별 1차 근거 데이터 계산
- AI 서버 연동
- 리포트 저장 및 조회
- 마이페이지 API
- 외부 API 및 인증 오류 처리

### AI

- FastAPI 기반 AI 서버 구축
- 백엔드와 주고받을 입출력 스키마 정의
- 백엔드·프론트엔드·AI·클라우드/인프라 직무별 분석 기준 설계
- 분석 목적별 프롬프트 설계
- 전체 진단 및 대표 프로젝트 추천
- 프로젝트별 보완 방향 생성
- GitHub 정리 로드맵 생성
- 면접 질문과 답변 가이드 생성
- 사용자 역할 기반 포트폴리오 문장 생성
- 근거 기반 생성 규칙과 품질 평가

---

## 주요 API 초안

### 현재 로그인 사용자 조회

```http
GET /api/me
```

### 내 public repository 목록 조회

```http
GET /api/me/repositories
```

### 분석 요청 생성

```http
POST /api/portfolio-analyses
```

요청 예시:

```json
{
  "repositoryNames": [
    "user/project-a",
    "user/project-b"
  ],
  "targetJob": "BACKEND",
  "analysisPurpose": "INTERVIEW_PREPARATION",
  "repositoryRoles": [
    {
      "repositoryName": "user/project-a",
      "projectType": "TEAM",
      "role": "Backend",
      "implementedFeatures": [
        "주문 생성 API",
        "운영자 주문 상태 변경 API"
      ],
      "relatedFiles": [
        "OrderController.java",
        "OrderService.java"
      ],
      "relatedPullRequests": [],
      "relatedCommits": []
    }
  ]
}
```

응답 예시:

```json
{
  "analysisId": 1,
  "status": "PENDING"
}
```

### 분석 상태 조회

```http
GET /api/portfolio-analyses/{analysisId}
```

### 분석 결과 조회

```http
GET /api/portfolio-analyses/{analysisId}/report
```

### 내 분석 기록 조회

```http
GET /api/me/portfolio-analyses
```

---

## MVP 범위

### 반드시 구현

- GitHub OAuth 로그인
- 사용자 정보 및 세션 관리
- Public repository 목록 조회
- 분석할 repository 선택
- 희망 직무 및 분석 목적 선택
- 개인/팀 프로젝트 구분
- 팀 프로젝트 역할 입력
- README 및 기술스택 근거 분석
- Dockerfile, GitHub Actions, 테스트 코드 존재 여부 확인
- 백엔드 1차 근거 데이터 구조화
- AI 포트폴리오 리포트 생성
- 분석 결과 저장
- 마이페이지에서 이전 결과 조회

### 제한적으로 구현

- 최근 commit 일부 조회
- 사용자 작성 commit 일부 조회
- 최근 PR 일부 조회
- PR 변경 파일 일부 조회
- 변경 파일 기반 활동 영역 후보 분류

### MVP에서 제외

- 개인 기여율 자동 계산
- GitHub 기록만을 이용한 사용자 실력 평가
- 전체 commit history 정밀 분석
- repository 전체 코드의 LLM 입력
- Private repository 분석
- README 자동 수정 PR 생성
- PR 자동 리뷰
- 채용공고 매칭
- PDF 다운로드
- 공유 리포트

---

## 데이터 및 AI 분석 제한

서비스 안정성과 비용 관리를 위해 다음 제한을 적용할 수 있습니다.

- 분석 repository 최대 3~5개
- 최근 commit 조회 개수 제한
- 최근 PR 조회 개수 제한
- 분석 대상 파일 수 제한
- 파일당 최대 크기 제한
- 바이너리 및 자동 생성 파일 제외
- AI 입력 토큰 제한
- 분석 요청 timeout 적용
- 동일 사용자의 동시 분석 요청 제한

---

## 분석 결과 주의사항

RepoMentor AI의 분석 결과는 공개 GitHub repository와 사용자가 입력한 정보를 바탕으로 생성한 포트폴리오 코칭 자료입니다.

다음 정보는 분석에 반영되지 않거나 정확히 확인하기 어려울 수 있습니다.

- Private repository
- 오프라인 프로젝트
- 실제 팀 내부 업무 분담
- pair programming 과정
- 다른 팀원이 대신 작성한 commit
- squash merge로 사라진 개별 기록
- GitHub 외부에서 이루어진 협업
- 실제 업무 역량과 문제 해결 능력

따라서 본 서비스는 사용자의 실력이나 취업 가능성을 단정하지 않으며, GitHub 포트폴리오를 더 효과적으로 정리하기 위한 참고 자료를 제공합니다.

---

## 개발 일정

| 주차 | 주요 내용 |
|---|---|
| 1주차 | 요구사항 및 기능 명세, 화면 흐름과 와이어프레임 |
| 2주차 | React, Spring Boot, PostgreSQL, FastAPI 개발 환경 구축 |
| 3주차 | 도메인 분석, ERD 및 API 명세 작성 |
| 4주차 | GitHub OAuth 로그인과 사용자 인증 |
| 5주차 | Public repository 조회 및 선택 화면 |
| 6주차 | 희망 직무, 분석 목적, 프로젝트 역할 입력 |
| 7주차 | 분석 요청 생성 및 상태 관리 |
| 8주차 | README, 파일 트리, 기술스택 근거 분석 |
| 9주차 | commit, PR 및 변경 파일 일부 수집 |
| 10주차 | 백엔드 1차 근거 데이터 계산과 AI 입력 구조 |
| 11주차 | FastAPI AI 서버와 리포트 생성 기능 |
| 12주차 | 백엔드와 AI 서버 연동 및 결과 저장 |
| 13주차 | AI 리포트 및 프로젝트별 상세 화면 |
| 14주차 | 마이페이지와 예외 처리 |
| 15주차 | 통합 테스트, 배포, 발표 및 문서화 |

---

## 프로젝트 구조 예시

```text
repomentor-ai/
├── frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── README.md
│
├── backend/
│   ├── src/
│   ├── build.gradle
│   └── README.md
│
├── ai-server/
│   ├── app/
│   ├── tests/
│   ├── requirements.txt
│   └── README.md
│
├── docs/
│   ├── api/
│   ├── architecture/
│   ├── erd/
│   └── wireframes/
│
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 실행 방법

> 현재 MVP 개발 전 단계이므로 상세 실행 명령은 각 파트의 초기 환경 구성이 완료된 뒤 추가할 예정입니다.

예상 실행 구조는 다음과 같습니다.

```bash
# Frontend
cd frontend
npm install
npm run dev
```

```bash
# Backend
cd backend
./gradlew bootRun
```

```bash
# AI Server
cd ai-server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

또는 Docker Compose를 사용하는 경우:

```bash
docker compose up --build
```

---

## 환경변수 예시

실제 키와 비밀값은 repository에 커밋하지 않습니다.

```env
# GitHub OAuth
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=

# Database
POSTGRES_DB=
POSTGRES_USER=
POSTGRES_PASSWORD=
DATABASE_URL=

# AI
LLM_API_KEY=
AI_SERVER_URL=

# Session / Security
SESSION_SECRET=
```

`.env.example`에는 변수 이름만 작성하고 실제 값은 로컬 환경 또는 배포 환경의 Secret으로 관리합니다.

---

## 향후 확장 계획

MVP 이후 다음 기능을 고려할 수 있습니다.

- GitHub OAuth 권한을 활용한 Private repository 분석
- GitHub App 연동
- README 개선안 생성
- README 개선 PR 자동 생성
- AI 면접 시뮬레이터
- 사용자 답변 평가 및 꼬리질문 생성
- 채용공고와 프로젝트 매칭
- 공유 가능한 포트폴리오 리포트
- PDF 다운로드
- 분석 전후 비교
- 프로젝트 설명 챗봇
- 커밋 및 PR 활동 요약
- Redis 기반 분석 상태 및 캐시 관리
- GitHub Actions 기반 CI/CD
- AWS 배포 및 모니터링

---

## 기대 효과

- 개발자 취업 준비생이 자신의 GitHub를 포트폴리오 관점에서 점검할 수 있습니다.
- 대표 프로젝트와 프로젝트별 보완 우선순위를 확인할 수 있습니다.
- README, 테스트, 배포, CI/CD 등 GitHub에서 부족하게 드러나는 부분을 파악할 수 있습니다.
- 희망 직무에 맞추어 프로젝트 경험을 정리할 수 있습니다.
- 프로젝트 기반 예상 면접 질문과 답변 가이드를 얻을 수 있습니다.
- GitHub OAuth, 외부 API, Spring Boot, React, FastAPI와 LLM API를 연동하는 실제 서비스 개발 경험을 쌓을 수 있습니다.

---

## 팀 구성

| 담당 | 역할 |
|---|---|
| Frontend | React 기반 사용자 화면 및 AI 리포트 시각화 |
| Backend | GitHub OAuth, 데이터 수집, 근거 계산, 상태 관리 및 결과 저장 |
| AI | 직무·목적별 프롬프트와 근거 기반 포트폴리오 코칭 리포트 생성 |

---

## 라이선스

라이선스는 프로
