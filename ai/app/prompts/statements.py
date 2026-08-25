from collections.abc import Sequence

from app.criteria.models import CriteriaSet
from app.domain import (
    AnalysisDepth,
    NormalizedRepositoryContext,
    PortfolioSynthesis,
    RepositoryAnalysis,
)
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

_DEPTH_RANK = {
    AnalysisDepth.P0: 0,
    AnalysisDepth.P1: 1,
    AnalysisDepth.P2: 2,
}

_STATEMENT_TASK_TEMPLATE = """
BACKEND × ENTRY × 최대 {analysis_depth} 범위에서 실제 포트폴리오에 재사용할 수 있는
PortfolioStatement를 최대 {statement_count}개 생성한다.

- 허용 statement_type은 RESUME, PORTFOLIO, INTERVIEW이다.
- 각 문장은 evidence_refs 또는 claim_refs 중 최소 하나를 포함한다.
- 각 문장은 입력에 존재하는 criterion_keys만 사용한다.
- Repository별 completedEvidenceLevels까지만 사용하고 완료되지 않은 깊이로 판단하지 않는다.
- 여러 Repository를 참조하는 문장은 가장 얕은 Repository 분석 깊이를 상한으로 사용한다.
- 입력에 없는 기술, 파일 경로, 기능 또는 구현 경험을 생성하지 않는다.
- UserClaim 기반 문장은 사용자 진술임을 자연어에서도 명시하고 GitHub에서 검증된 사실로
  승격하지 않는다.
- Evidence와 UserClaim을 함께 사용해도 두 근거 유형의 의미를 혼동하지 않는다.
- P0에서는 README, 의존성·설정, 테스트 파일, Docker와 GitHub Actions의 관찰 범위만 사용한다.
- P1에서는 전달된 Commit, PR과 변경 경로의 관찰 범위만 사용하고 활동량을 개인 기여도나
  실력으로 해석하지 않는다.
- P2에서는 전달된 CODE_EVIDENCE snippet에서 직접 관찰되는 내용만 사용하고 Repository 전체
  코드·설계·테스트 품질로 일반화하지 않는다.
- NOT_OBSERVED를 실제 부재, 거짓 또는 미기여로 해석하지 않는다.
- 사용자 역량, 경력 수준 충족 여부, 취업 가능성 또는 합격 가능성을 단정하지 않는다.
- 전달된 코드를 실행하지 않는다.
- Recommendation, InterviewQuestion, PortfolioAnalysis, InternalPortfolioReport,
  generation_records, HTTP Response와 Error Envelope는 생성하지 않는다.
- 응답은 Provider가 전달한 PortfolioStatementBatch Structured Output Schema를 따른다.
""".strip()

_CORRECTION_TASK_TEMPLATE = """
{base_task}

이전 생성 결과가 다음 정책 위반 코드로 거절되었다.
{violation_codes}

- 이전 결과를 수정하거나 일부 문장만 삭제하지 않는다.
- 입력 Evidence, UserClaim, RepositoryAnalysis와 PortfolioSynthesis만 사용해
  PortfolioStatementBatch 전체를 처음부터 다시 생성한다.
- 위반 코드에 해당하는 정책을 모두 준수한다.
- 이전 응답의 문장, 오류 메시지 또는 필드 경로를 추정하거나 재현하지 않는다.
""".strip()


def build_statement_prompt(
    contexts: Sequence[NormalizedRepositoryContext],
    repository_analyses: Sequence[RepositoryAnalysis],
    synthesis: PortfolioSynthesis,
    criteria: CriteriaSet,
    *,
    statement_count: int = 6,
) -> str:
    """Build a grounded prompt for reusable portfolio statements."""

    context_items, analysis_items, maximum_depth = _prepare_statement_inputs(
        contexts,
        repository_analyses,
        synthesis,
        criteria,
        statement_count,
    )
    task = _STATEMENT_TASK_TEMPLATE.format(
        analysis_depth=maximum_depth.value,
        statement_count=statement_count,
    )
    return _render_statement_prompt(
        context_items,
        analysis_items,
        synthesis,
        criteria,
        task,
    )


def build_statement_correction_prompt(
    contexts: Sequence[NormalizedRepositoryContext],
    repository_analyses: Sequence[RepositoryAnalysis],
    synthesis: PortfolioSynthesis,
    criteria: CriteriaSet,
    violation_codes: Sequence[PolicyViolationCode],
    *,
    statement_count: int = 6,
) -> str:
    """Build a full statement regeneration prompt using stable policy codes only."""

    unique_codes = tuple(dict.fromkeys(violation_codes))
    if not unique_codes:
        raise PromptContextError("Statement correction requires a policy violation code.")

    context_items, analysis_items, maximum_depth = _prepare_statement_inputs(
        contexts,
        repository_analyses,
        synthesis,
        criteria,
        statement_count,
    )
    base_task = _STATEMENT_TASK_TEMPLATE.format(
        analysis_depth=maximum_depth.value,
        statement_count=statement_count,
    )
    task = _CORRECTION_TASK_TEMPLATE.format(
        base_task=base_task,
        violation_codes="\n".join(f"- {code.value}" for code in unique_codes),
    )
    return _render_statement_prompt(
        context_items,
        analysis_items,
        synthesis,
        criteria,
        task,
    )


def _prepare_statement_inputs(
    contexts: Sequence[NormalizedRepositoryContext],
    repository_analyses: Sequence[RepositoryAnalysis],
    synthesis: PortfolioSynthesis,
    criteria: CriteriaSet,
    statement_count: int,
) -> tuple[
    tuple[NormalizedRepositoryContext, ...],
    tuple[RepositoryAnalysis, ...],
    AnalysisDepth,
]:
    context_items = tuple(contexts)
    analysis_items = tuple(repository_analyses)
    if not 1 <= len(context_items) <= 5:
        raise PromptContextError("Statement prompt requires one to five repository contexts.")
    if not 1 <= len(analysis_items) <= 5:
        raise PromptContextError("Statement prompt requires one to five repository analyses.")

    context_names = [item.repository_full_name for item in context_items]
    analysis_names = [item.repository_full_name for item in analysis_items]
    if len(context_names) != len(set(context_names)):
        raise PromptContextError("Statement context names must be unique.")
    if len(analysis_names) != len(set(analysis_names)):
        raise PromptContextError("Statement analysis names must be unique.")
    if set(context_names) != set(analysis_names):
        raise PromptContextError(
            "Statement contexts and analyses must reference the same repositories."
        )

    representative_names = {
        project.repository_full_name for project in synthesis.representative_projects
    }
    if not representative_names.issubset(set(context_names)):
        raise PromptContextError(
            "Statement synthesis representative projects must reference supplied repositories."
        )

    if (
        isinstance(statement_count, bool)
        or not isinstance(statement_count, int)
        or not 1 <= statement_count <= 15
    ):
        raise PromptContextError("Statement count must be an integer between one and fifteen.")

    maximum_depth = max(
        (context.analysis_depth for context in context_items),
        key=_DEPTH_RANK.__getitem__,
    )
    if criteria.analysis_depth is not maximum_depth:
        raise PromptContextError(
            "Statement criteria must match the deepest repository analysis depth."
        )

    return context_items, analysis_items, maximum_depth


def _render_statement_prompt(
    contexts: Sequence[NormalizedRepositoryContext],
    repository_analyses: Sequence[RepositoryAnalysis],
    synthesis: PortfolioSynthesis,
    criteria: CriteriaSet,
    task: str,
) -> str:
    repository_data = [build_repository_data(context) for context in contexts]
    prior_analysis = {
        "repository_analyses": repository_analyses,
        "portfolio_synthesis": synthesis,
    }
    return "\n\n".join(
        (
            render_section(CRITERIA_SECTION, serialize_criteria(criteria)),
            render_section(
                REPOSITORY_DATA_SECTION,
                serialize_untrusted_data({"repositories": repository_data}),
            ),
            render_section(
                PRIOR_ANALYSIS_SECTION,
                serialize_untrusted_data(prior_analysis),
            ),
            render_section(TASK_SECTION, task),
        )
    )


__all__ = ["build_statement_correction_prompt", "build_statement_prompt"]
