from app.criteria.models import CriteriaSet
from app.domain import NormalizedRepositoryContext, RepositoryAnalysis
from app.prompts.context import (
    CRITERIA_SECTION,
    PRIOR_ANALYSIS_SECTION,
    REPOSITORY_DATA_SECTION,
    TASK_SECTION,
    PromptContextError,
    build_repository_data,
    render_section,
    serialize_criteria,
    serialize_untrusted_data,
)

_INTERVIEW_TASK_TEMPLATE = """
BACKEND × ENTRY × P0 범위에서 최대 {question_count}개의 프로젝트 기반 InterviewQuestion을 생성한다.

- 각 질문에 면접관 의도, 답변 방향, 필요한 경우 꼬리질문을 포함한다.
- Evidence 기반 질문은 evidence_refs를 포함한다.
- UserClaim 기반 질문은 claim_refs를 포함하고 검증된 GitHub 사실처럼 표현하지 않는다.
- 입력에 없는 기술, 파일, 기능과 구현 경험을 질문의 전제로 사용하지 않는다.
- 코드 품질, 설계 품질, 테스트 품질, 보안 품질을 확인된 사실로 전제하지 않는다.
- commit 수나 변경량을 개인 기여도 또는 실력 질문으로 변환하지 않는다.
- NOT_OBSERVED를 실제 부재, 거짓 또는 미기여로 해석하지 않는다.
- 경력 수준 충족 여부, 취업 가능성과 합격 가능성을 판단하지 않는다.
- 응답은 Provider가 전달한 InterviewQuestion 목록 Structured Output Schema를 따른다.
""".strip()


def build_interview_prompt(
    context: NormalizedRepositoryContext,
    repository_analysis: RepositoryAnalysis,
    criteria: CriteriaSet,
    *,
    question_count: int = 5,
) -> str:
    """Build the user prompt for grounded P0 interview questions."""

    if context.repository_full_name != repository_analysis.repository_full_name:
        raise PromptContextError(
            "Interview context and analysis must reference the same repository."
        )
    if isinstance(question_count, bool) or not 1 <= question_count <= 10:
        raise PromptContextError("Interview question count must be between one and ten.")

    task = _INTERVIEW_TASK_TEMPLATE.format(question_count=question_count)
    return "\n\n".join(
        (
            render_section(CRITERIA_SECTION, serialize_criteria(criteria)),
            render_section(
                REPOSITORY_DATA_SECTION,
                serialize_untrusted_data(build_repository_data(context)),
            ),
            render_section(
                PRIOR_ANALYSIS_SECTION,
                serialize_untrusted_data(repository_analysis),
            ),
            render_section(TASK_SECTION, task),
        )
    )
