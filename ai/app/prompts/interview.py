from collections.abc import Sequence

from app.criteria.models import CriteriaSet
from app.domain import AnalysisDepth, NormalizedRepositoryContext, RepositoryAnalysis
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
from app.validators.report_validator import PolicyViolationCode

_INTERVIEW_TASK_TEMPLATE = """
BACKEND × ENTRY × {analysis_depth} 범위에서 최대 {question_count}개의 프로젝트 기반
InterviewQuestion을 생성한다.
이 Repository에서 완료된 Evidence 깊이는 {completed_levels}이며 이 범위를 넘어 질문하지 않는다.

- 각 질문에 면접관 의도, 답변 방향, 필요한 경우 꼬리질문을 포함한다.
- Evidence 기반 질문은 evidence_refs를 포함한다.
- UserClaim 기반 질문은 claim_refs를 포함하고 검증된 GitHub 사실처럼 표현하지 않는다.
- 입력에 없는 기술, 파일, 기능과 구현 경험을 질문의 전제로 사용하지 않는다.
- P1의 Commit 수나 변경량을 개인 기여도 또는 실력 질문으로 변환하지 않는다.
- P2 snippet 밖의 코드, 호출 관계 또는 Repository 전체 품질을 질문의 전제로 사용하지 않는다.
- 전달된 코드를 실행하지 않는다.
- NOT_OBSERVED를 실제 부재, 거짓 또는 미기여로 해석하지 않는다.
- relatedEvidenceRefs가 비어 있어도 UserClaim을 거짓 또는 미기여로 해석하지 않는다.
- 경력 수준 충족 여부, 취업 가능성과 합격 가능성을 판단하지 않는다.
{depth_rules}
- 응답은 Provider가 전달한 InterviewQuestionBatch Structured Output Schema를 따른다.
""".strip()

_P0_INTERVIEW_RULES = """
- P0에서는 README, 의존성·설정, 테스트 파일, Docker와 GitHub Actions 근거만 질문 소재로 사용한다.
- P0만으로 코드 품질, 설계 품질, 테스트 품질 또는 보안 품질을 전제하지 않는다.
""".strip()

_P1_INTERVIEW_RULES = """
- P1에서는 전달된 Commit, PR과 변경 경로에서 관찰되는 활동 소재를 질문에 사용할 수 있다.
""".strip()

_P2_INTERVIEW_RULES = """
- P2에서는 CODE_EVIDENCE snippet에서 직접 보이는 입력 검증, 오류 처리, 책임과
  테스트 사례만 질문 소재로 사용한다.
""".strip()

_CORRECTION_TASK_TEMPLATE = """
{base_task}

이전 생성 결과가 다음 정책 위반 코드로 거절되었다.
{violation_codes}

- 이전 결과의 일부 질문을 삭제하거나 수정하지 않는다.
- 입력 Evidence, UserClaim과 RepositoryAnalysis만 사용해 InterviewQuestionBatch 전체를
  처음부터 다시 생성한다.
- 위반 코드에 해당하는 정책을 모두 준수한다.
- 이전 응답의 문장, 오류 메시지 또는 필드 경로를 추정하거나 재현하지 않는다.
""".strip()


def build_interview_prompt(
    context: NormalizedRepositoryContext,
    repository_analysis: RepositoryAnalysis,
    criteria: CriteriaSet,
    *,
    question_count: int = 5,
) -> str:
    """Build the user prompt for depth-scoped grounded interview questions."""

    _validate_interview_inputs(context, repository_analysis, criteria, question_count)

    task = _build_interview_task(context, question_count)
    return _render_interview_prompt(context, repository_analysis, criteria, task)


def build_interview_correction_prompt(
    context: NormalizedRepositoryContext,
    repository_analysis: RepositoryAnalysis,
    criteria: CriteriaSet,
    violation_codes: Sequence[PolicyViolationCode],
    *,
    question_count: int = 5,
) -> str:
    """Build a full interview regeneration prompt using stable policy codes only."""

    _validate_interview_inputs(context, repository_analysis, criteria, question_count)
    unique_codes = tuple(dict.fromkeys(violation_codes))
    if not unique_codes:
        raise PromptContextError("Interview correction requires a policy violation code.")

    task = _CORRECTION_TASK_TEMPLATE.format(
        base_task=_build_interview_task(context, question_count),
        violation_codes="\n".join(f"- {code.value}" for code in unique_codes),
    )
    return _render_interview_prompt(context, repository_analysis, criteria, task)


def _validate_interview_inputs(
    context: NormalizedRepositoryContext,
    repository_analysis: RepositoryAnalysis,
    criteria: CriteriaSet,
    question_count: int,
) -> None:
    if context.repository_full_name != repository_analysis.repository_full_name:
        raise PromptContextError(
            "Interview context and analysis must reference the same repository."
        )
    if (
        isinstance(question_count, bool)
        or not isinstance(question_count, int)
        or not 1 <= question_count <= 10
    ):
        raise PromptContextError("Interview question count must be between one and ten.")
    if context.analysis_depth is not criteria.analysis_depth:
        raise PromptContextError("Interview context and criteria must use the same analysis depth.")


def _render_interview_prompt(
    context: NormalizedRepositoryContext,
    repository_analysis: RepositoryAnalysis,
    criteria: CriteriaSet,
    task: str,
) -> str:
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


def _build_interview_task(
    context: NormalizedRepositoryContext,
    question_count: int,
) -> str:
    depth_rules = [_P0_INTERVIEW_RULES]
    if context.analysis_depth in {AnalysisDepth.P1, AnalysisDepth.P2}:
        depth_rules.append(_P1_INTERVIEW_RULES)
    if context.analysis_depth is AnalysisDepth.P2:
        depth_rules.append(_P2_INTERVIEW_RULES)

    return _INTERVIEW_TASK_TEMPLATE.format(
        analysis_depth=context.analysis_depth.value,
        question_count=question_count,
        completed_levels=",".join(level.value for level in context.completed_evidence_levels),
        depth_rules="\n".join(depth_rules),
    )
