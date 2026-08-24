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

_PORTFOLIO_TASK_TEMPLATE = """
BACKEND × ENTRY × 최대 {analysis_depth} 범위에서 Repository별 분석을 종합한
PortfolioAnalysis를 생성한다.

- 각 Repository의 completedEvidenceLevels까지만 사용하고 완료되지 않은 깊이로 판단하지 않는다.
- 한 Repository의 Evidence를 다른 Repository의 근거로 사용하지 않는다.
- 전체 포트폴리오 진단과 Repository별 실제 분석 한계를 제시한다.
- 대표 프로젝트는 제공된 Repository 중에서만 선택하고 Evidence 또는 UserClaim을 참조한다.
- job_appeal 항목은 공개 Evidence만 참조하며 UserClaim만으로 확정하지 않는다.
- 전체 개선 제안은 RECOMMENDATION으로 만들고 Evidence를 최소 하나 참조한다.
- PortfolioStatement는 Evidence 또는 UserClaim을 최소 하나 참조한다.
- UserClaim만 사용하는 문장은 사용자 진술 기반이라는 구분을 유지한다.
- 이전 RepositoryAnalysis와 입력 데이터에 없는 새로운 사실을 생성하지 않는다.
- P1 활동량을 실력이나 개인 기여율로 해석하지 않는다.
- P2 snippet을 Repository 전체 코드·설계·테스트 품질로 일반화하지 않는다.
- 전달된 코드를 실행하지 않는다.
- InterviewQuestion은 별도 Interview Prompt에서 생성하므로 필수로 생성하지 않는다.
- 프로젝트 점수, 개인 기여율, 사용자 역량을 생성하지 않는다.
- 경력 수준 충족 여부, 취업 또는 합격 가능성을 생성하지 않는다.
- 응답은 Provider가 전달한 PortfolioAnalysis Structured Output Schema를 따른다.
""".strip()


def build_portfolio_prompt(
    contexts: Sequence[NormalizedRepositoryContext],
    repository_analyses: Sequence[RepositoryAnalysis],
    criteria: CriteriaSet,
) -> str:
    """Build the user prompt for P0 portfolio aggregation."""

    ordered_contexts, ordered_analyses = _validate_and_order_inputs(
        contexts,
        repository_analyses,
    )
    maximum_depth = _maximum_context_depth(ordered_contexts)
    if criteria.analysis_depth is not maximum_depth:
        raise PromptContextError(
            "Portfolio criteria must match the deepest repository analysis depth."
        )
    repository_data = [build_repository_data(context) for context in ordered_contexts]
    task = _PORTFOLIO_TASK_TEMPLATE.format(analysis_depth=maximum_depth.value)

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
