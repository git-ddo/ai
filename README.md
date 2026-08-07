# GitDdo AI Server

공개 GitHub Repository의 근거와 사용자 입력을 바탕으로 취업용 포트폴리오 코칭 리포트를 생성하는 AI 서버 저장소이다.

## 주요 기능

- Repository별 포트폴리오 분석
- 전체 포트폴리오 진단과 대표 프로젝트 추천
- 희망 직무별 보완 방향과 GitHub 정리 로드맵 생성
- 프로젝트 기반 면접 질문과 답변 가이드 생성
- 이력서·포트폴리오용 문장 생성
- LLM 응답의 Schema 및 근거 검증

## 데이터 흐름

```text
Spring Boot Backend
  → GitHub 근거 + 백엔드 계산 지표 + 사용자 입력
FastAPI AI Server
  → 입력 검증 + Prompt 선택 + LLM 호출 + 근거 검증
Spring Boot Backend
  → 리포트 저장 및 Frontend 제공
```

## 핵심 원칙

분석 결과에서는 다음 정보를 명확히 구분한다.

1. GitHub에서 확인된 객관적 근거
2. 사용자가 직접 입력한 역할과 경험
3. 백엔드가 계산한 지표
4. AI가 생성한 해석과 제안

입력에 없는 기술이나 파일을 사실처럼 생성하지 않으며, commit 수를 개인 기여도나 실력으로 해석하지 않는다.

## 기술 스택

- Python 3.12+
- FastAPI, Uvicorn
- Pydantic v2
- OpenAI Structured Outputs
- pytest, Ruff, type checker
- Docker, GitHub Actions