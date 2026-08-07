# GitHub 협업 규칙

이 문서는 AI 서버를 공동 개발할 때 사용하는 GitHub 작업 규칙이다. 모든 변경은 추적 가능하고 검토 가능한 단위로 관리하며, `main` 브랜치는 항상 실행 및 검증 가능한 상태를 유지한다.

## 1. 기본 원칙

- `main` 브랜치에 직접 commit하거나 push하지 않는다.
- 모든 작업은 Issue를 기준으로 시작하고 별도 branch에서 진행한다.
- 하나의 branch와 Pull Request는 하나의 목적만 가진다.
- 변경은 기능, 테스트, 문서, 리팩터링처럼 논리적인 작업 단위로 commit한다.
- 코드 변경에는 필요한 테스트와 문서 변경을 함께 포함한다.
- 다른 사람의 작업이나 기존 미커밋 변경을 임의로 수정하거나 되돌리지 않는다.
- API key, token, 실제 `.env` 및 개인정보는 commit하지 않는다.
- merge 전에 필수 검사와 리뷰를 통과해야 한다.

## 2. 작업 흐름

```text
Issue 생성
  → 담당자와 범위 확정
  → 최신 main에서 branch 생성
  → 작은 작업 단위로 구현 및 commit
  → 로컬 검증
  → remote branch push
  → Pull Request 생성
  → CI와 코드 리뷰
  → 승인 후 merge
  → 작업 branch 삭제
```

## 3. Issue 규칙

코드나 문서를 변경하기 전에 Issue에 작업 목적과 완료 조건을 기록한다.

Issue에는 다음 내용을 포함한다.

- 배경과 해결하려는 문제
- 작업 범위
- 작업에서 제외할 범위
- 예상 변경 파일 또는 모듈
- 완료 조건
- 관련 API 계약이나 참고 문서

권장 Issue 제목 형식은 다음과 같다.

```text
[Feature] FastAPI health check 추가
[Fix] 잘못된 LLM JSON 응답 처리
[Docs] 백엔드 연동 API 계약 정리
[Test] Evidence Validator 경계 조건 추가
[Refactor] Prompt Router 책임 분리
```

작업 중 범위가 크게 달라지면 기존 Issue를 조용히 확장하지 않는다. Issue 설명을 갱신하거나 별도 Issue로 분리한다.

## 4. Branch 규칙

branch는 최신 `main`에서 생성한다.

```bash
git switch main
git pull --ff-only origin main
git switch -c feat/12-health-check
```

branch 이름은 다음 형식을 사용한다.

```text
<type>/<issue-number>-<short-description>
```

사용 가능한 type은 다음과 같다.

| Type | 용도 | 예시 |
|---|---|---|
| `feat` | 새로운 기능 | `feat/12-health-check` |
| `fix` | 버그 수정 | `fix/21-invalid-json` |
| `docs` | 문서 변경 | `docs/8-api-contract` |
| `test` | 테스트 추가·수정 | `test/31-evidence-validator` |
| `refactor` | 동작 변경 없는 구조 개선 | `refactor/17-prompt-router` |
| `chore` | 설정, 의존성, 도구 변경 | `chore/5-ruff-config` |

branch 이름은 영문 소문자와 숫자, 하이픈을 사용한다. 여러 작업을 하나의 장기 branch에 누적하지 않는다.

## 5. Commit 규칙

하나의 commit에는 하나의 논리적 변경만 포함한다. 서로 독립적으로 설명하거나 되돌릴 필요가 있는 변경은 별도 commit으로 나눈다.

commit 전 다음 내용을 확인한다.

```bash
git status --short
git diff
git diff --staged
```

파일 전체를 무조건 staging하지 않고 현재 작업에 필요한 파일만 명시적으로 추가한다.

```bash
git add ai/app/main.py ai/tests/test_health.py
```

commit 메시지는 다음 형식을 사용한다.

```text
<type>: <변경 목적>
```

예시는 다음과 같다.

```text
feat: health check API 추가
fix: LLM timeout 예외 변환 수정
test: 근거 없는 기술 검출 사례 추가
docs: 포트폴리오 리포트 스키마 명세 추가
refactor: prompt 선택 로직을 router로 분리
chore: Ruff 검사 규칙 설정
```

다음 commit은 피한다.

- `수정`, `작업`, `update`처럼 목적을 알 수 없는 메시지
- 기능 구현과 무관한 포맷 변경을 섞은 commit
- 테스트가 실패하는 중간 상태를 공유 branch에 남기는 commit
- 다른 작업자의 파일이나 개인 설정을 포함한 commit
- 비밀값을 삭제했다는 이유만으로 해당 비밀값이 포함된 이력을 push하는 것

## 6. Pull Request 규칙

Pull Request는 가능한 한 작게 유지한다. 리뷰어가 한 가지 목적과 데이터 흐름을 이해할 수 있는 크기가 기준이다.

PR 제목은 Issue 또는 commit과 동일한 type을 사용한다.

```text
feat: health check API 추가
```

PR 본문에는 다음 내용을 포함한다.

```markdown
## 관련 Issue

- Closes #12

## 변경 내용

- 변경한 기능과 파일

## 동작 원리

- 요청부터 응답까지의 처리 흐름

## 검증

- 실행한 lint, type check, test와 결과

## 확인 필요 사항

- 리뷰어가 집중해서 볼 부분과 남은 제한사항
```

다음 조건을 만족한 뒤 리뷰를 요청한다.

- PR 범위와 무관한 변경이 없음
- formatter와 lint 통과
- type check 통과
- 관련 test 통과
- 비밀정보와 불필요한 생성 파일이 없음
- API 계약 변경 시 관련 문서와 예제 갱신
- 사용자에게 영향을 주는 변경은 동작과 제한사항 설명

구현이 아직 끝나지 않았거나 설계 피드백이 필요한 경우 Draft PR을 사용한다.

## 7. 리뷰 규칙

리뷰는 사람을 평가하는 과정이 아니라 코드의 정확성, 유지보수성 및 안전성을 함께 확인하는 과정이다.

리뷰어는 다음 항목을 확인한다.

- AI 서버의 책임 범위를 벗어나지 않는가
- 요청과 응답이 Pydantic Schema와 일치하는가
- GitHub 근거, 사용자 입력 및 AI 제안을 구분하는가
- 입력에 없는 기술이나 파일을 사실처럼 생성할 가능성이 없는가
- timeout, rate limit, 잘못된 JSON 등 실패 흐름을 처리하는가
- 테스트가 정상 흐름과 주요 경계 조건을 검증하는가
- API key, token 또는 민감한 원문이 로그에 노출되지 않는가

리뷰 의견은 다음 수준으로 구분한다.

- `blocking`: merge 전에 반드시 수정해야 하는 문제
- `suggestion`: 품질 향상을 위한 제안
- `question`: 의도나 설계를 확인하기 위한 질문
- `nit`: 선택적으로 반영할 수 있는 사소한 의견

작성자는 리뷰 의견에 수정 commit 또는 설명으로 응답한다. 해결하지 않은 `blocking` 의견이 남아 있으면 merge하지 않는다.

## 8. Merge 규칙

- CI가 모두 통과하고 최소 1명의 승인을 받은 뒤 merge한다.
- 작성자가 단독으로 작성하고 승인한 PR을 바로 merge하지 않는다.
- 기본 방식은 Squash merge를 사용하여 `main`에 PR 단위의 명확한 이력을 남긴다.
- Squash commit 제목은 PR 제목과 동일한 형식을 사용한다.
- merge 직전 `main`과 충돌하거나 API 계약이 바뀌었으면 다시 검증한다.
- merge 후 remote와 local의 작업 branch를 정리한다.

긴급 수정이라도 가능한 한 Issue와 PR을 생략하지 않는다. 서비스 장애로 절차를 축소했다면 이후 Issue에 원인, 변경 내용 및 검증 결과를 기록한다.

## 9. 충돌 해결

- 충돌이 발생하면 파일의 최신 의도와 양쪽 변경 목적을 먼저 확인한다.
- 다른 작업자의 변경을 이해하지 못한 상태에서 임의로 한쪽을 선택하지 않는다.
- API Schema, Prompt 또는 Criteria 충돌은 관련 작업자와 계약을 다시 확인한다.
- 충돌 해결 후 영향받은 lint, type check 및 test를 다시 실행한다.
- 강제 push가 필요한 rebase는 공동 작업자와 합의한 개인 작업 branch에서만 수행한다.
- `main`과 다른 사람의 branch에는 강제 push하지 않는다.

## 10. AI 코딩 에이전트 사용 규칙

- AI 에이전트는 작업 시작 전 `README.md`, `AGENTS.md` 및 관련 `docs/` 문서를 확인한다.
- AI 에이전트가 생성한 코드도 사람이 작성한 코드와 동일한 리뷰와 테스트 기준을 적용한다.
- 에이전트는 사용자가 요청하거나 현재 작업에서 허용한 경우에만 commit한다.
- 에이전트는 사용자의 명시적 요청 없이 `push`, merge, rebase, PR 생성 또는 branch 삭제를 수행하지 않는다.
- 에이전트는 기존 미커밋 변경을 임의로 staging하거나 자신의 commit에 포함하지 않는다.
- 작업 완료 시 변경 파일, commit 여부, 검증 결과 및 남은 변경을 보고한다.

## 11. 저장소 보호 권장 설정

GitHub의 `main` branch에 다음 보호 규칙을 설정하는 것을 권장한다.

- Pull Request를 통한 변경만 허용
- merge 전 승인 최소 1명 요구
- 새로운 commit이 추가되면 기존 승인 무효화
- 필수 CI 검사 통과 요구
- unresolved conversation이 있으면 merge 차단
- force push 및 branch 삭제 금지
- 관리자도 가능하면 동일한 보호 규칙 적용

초기 필수 CI 검사는 다음과 같이 구성한다.

```text
Ruff format check
Ruff lint
type check
pytest
```

## 12. 완료 기준

작업은 다음 조건을 모두 만족할 때 완료된 것으로 본다.

- Issue의 완료 조건 충족
- 구현과 테스트 작성 완료
- formatter, lint, type check 및 test 통과
- 관련 문서와 API 계약 갱신
- PR 리뷰 의견 해결
- CI 통과 및 승인 후 merge
- merge 후 작업 branch 정리
