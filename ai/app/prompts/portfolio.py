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

_PORTFOLIO_TASK_TEMPLATE = """
BACKEND × ENTRY × 최대 {analysis_depth} 범위에서 Repository별 분석을 종합한
PortfolioSynthesis를 생성한다.

- 각 Repository의 completedEvidenceLevels까지만 사용하고 완료되지 않은 깊이로 판단하지 않는다.
- 한 Repository의 Evidence를 다른 Repository의 근거로 사용하지 않는다.
- 전체 포트폴리오 진단과 Repository별 실제 분석 한계를 제시한다.
- overall_summary, representative_projects, strengths, gaps, next_actions, job_appeal,
  limitations만 생성한다.
- overall_summary, strengths, gaps의 item_type은 INTERPRETATION으로 생성한다.
- next_actions의 item_type은 RECOMMENDATION으로 생성한다.
- job_appeal의 item_type은 JOB_APPEAL로 생성한다.
- 대표 프로젝트는 제공된 Repository 중에서만 선택하고, 해당 Repository의
  Evidence 또는 UserClaim만 참조한다.
- strengths, gaps, next_actions, job_appeal은 공개 Evidence를 최소 하나 참조한다.
- strengths와 단일 객체 job_appeal은 UserClaim만으로 확정하지 않는다.
- 누락을 기반으로 gaps 또는 next_actions을 생성하려면 명시적인
  BACKEND_DERIVED Evidence를 참조한다.
- NOT_OBSERVED는 실제 부재, 거짓 또는 미기여를 의미하지 않는다.
- 이전 RepositoryAnalysis와 입력 데이터에 없는 새로운 사실을 생성하지 않는다.
- P1 활동량을 실력이나 개인 기여율로 해석하지 않는다.
- P2 snippet을 Repository 전체 코드·설계·테스트 품질로 일반화하지 않는다.
- 전달된 코드를 실행하지 않는다.
- repository_analyses, interview_questions, portfolio_statements, generation_records, HTTP Response
  필드와 Error Envelope는 생성하지 않는다.
- 프로젝트 점수, 개인 기여율, 사용자 역량을 생성하지 않는다.
- 경력 수준 충족 여부, 취업 또는 합격 가능성을 생성하지 않는다.
- 응답은 Provider가 전달한 PortfolioSynthesis Structured Output Schema를 따른다.
""".strip()

_CORRECTION_TASK_TEMPLATE = """
{base_task}

이전 생성 결과가 다음 정책 위반 코드로 거절되었다.
{violation_codes}

- 이전 결과를 수정하거나 일부 항목을 삭제하지 않는다.
- 입력 Evidence, UserClaim과 검증된 RepositoryAnalysis만 사용해 PortfolioSynthesis 전체를
  처음부터 다시 생성한다.
- 위반 코드에 해당하는 정책을 모두 준수한다.
- 이전 응답의 문장, 오류 메시지 또는 필드 경로를 추정하거나 재현하지 않는다.
""".strip()


def build_portfolio_prompt(
    contexts: Sequence[NormalizedRepositoryContext],
    repository_analyses: Sequence[RepositoryAnalysis],
    criteria: CriteriaSet,
) -> str:
    """Build the user prompt for depth-aware portfolio synthesis."""

    ordered_contexts, ordered_analyses, maximum_depth = _prepare_portfolio_inputs(
        contexts,
        repository_analyses,
        criteria,
    )
    task = _PORTFOLIO_TASK_TEMPLATE.format(analysis_depth=maximum_depth.value)
    return _render_portfolio_prompt(
        ordered_contexts,
        ordered_analyses,
        criteria,
        task,
    )


def build_portfolio_correction_prompt(
    contexts: Sequence[NormalizedRepositoryContext],
    repository_analyses: Sequence[RepositoryAnalysis],
    criteria: CriteriaSet,
    violation_codes: Sequence[PolicyViolationCode],
) -> str:
    """Build a full-regeneration prompt using only stable policy codes."""

    unique_codes = tuple(dict.fromkeys(violation_codes))
    if not unique_codes:
        raise PromptContextError("Portfolio correction requires a policy violation code.")

    ordered_contexts, ordered_analyses, maximum_depth = _prepare_portfolio_inputs(
        contexts,
        repository_analyses,
        criteria,
    )
    base_task = _PORTFOLIO_TASK_TEMPLATE.format(analysis_depth=maximum_depth.value)
    task = _CORRECTION_TASK_TEMPLATE.format(
        base_task=base_task,
        violation_codes="\n".join(f"- {code.value}" for code in unique_codes),
    )
    return _render_portfolio_prompt(
        ordered_contexts,
        ordered_analyses,
        criteria,
        task,
    )


def _prepare_portfolio_inputs(
    contexts: Sequence[NormalizedRepositoryContext],
    repository_analyses: Sequence[RepositoryAnalysis],
    criteria: CriteriaSet,
) -> tuple[
    tuple[NormalizedRepositoryContext, ...],
    tuple[RepositoryAnalysis, ...],
    AnalysisDepth,
]:
    ordered_contexts, ordered_analyses = _validate_and_order_inputs(
        contexts,
        repository_analyses,
    )
    maximum_depth = _maximum_context_depth(ordered_contexts)
    if criteria.analysis_depth is not maximum_depth:
        raise PromptContextError(
            "Portfolio criteria must match the deepest repository analysis depth."
        )
    return ordered_contexts, ordered_analyses, maximum_depth


def _render_portfolio_prompt(
    ordered_contexts: Sequence[NormalizedRepositoryContext],
    ordered_analyses: Sequence[RepositoryAnalysis],
    criteria: CriteriaSet,
    task: str,
) -> str:
    repository_data = [build_repository_data(context) for context in ordered_contexts]

    return "\n\n".join(
        (
            render_section(CRITERIA_SECTION, serialize_criteria(criteria)),
            render_section(
                REPOSITORY_DATA_SECTION,
                serialize_untrusted_data({"repositories": repository_data}),
            ),
            render_section(
                PRIOR_ANALYSIS_SECTION,
                serialize_untrusted_data(ordered_analyses),
            ),
            render_section(TASK_SECTION, task),
        )
    )


def _validate_and_order_inputs(
    contexts: Sequence[NormalizedRepositoryContext],
    repository_analyses: Sequence[RepositoryAnalysis],
) -> tuple[tuple[NormalizedRepositoryContext, ...], tuple[RepositoryAnalysis, ...]]:
    context_items = tuple(contexts)
    analysis_items = tuple(repository_analyses)
    if not 1 <= len(context_items) <= 5:
        raise PromptContextError("Portfolio prompt requires one to five repository contexts.")
    if not 1 <= len(analysis_items) <= 5:
        raise PromptContextError("Portfolio prompt requires one to five repository analyses.")

    context_names = [item.repository_full_name for item in context_items]
    analysis_names = [item.repository_full_name for item in analysis_items]
    if len(context_names) != len(set(context_names)):
        raise PromptContextError("Repository context names must be unique.")
    if len(analysis_names) != len(set(analysis_names)):
        raise PromptContextError("Repository analysis names must be unique.")
    if set(context_names) != set(analysis_names):
        raise PromptContextError(
            "Repository contexts and analyses must reference the same repositories."
        )

    return (
        tuple(sorted(context_items, key=lambda item: item.repository_full_name)),
        tuple(sorted(analysis_items, key=lambda item: item.repository_full_name)),
    )


def _maximum_context_depth(
    contexts: Sequence[NormalizedRepositoryContext],
) -> AnalysisDepth:
    depth_rank = {
        AnalysisDepth.P0: 0,
        AnalysisDepth.P1: 1,
        AnalysisDepth.P2: 2,
    }
    return max((context.analysis_depth for context in contexts), key=depth_rank.__getitem__)
