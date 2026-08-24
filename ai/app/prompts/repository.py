from app.criteria.models import CriteriaSet
from app.domain import AnalysisDepth, NormalizedRepositoryContext
from app.prompts.context import (
    CRITERIA_SECTION,
    REPOSITORY_DATA_SECTION,
    TASK_SECTION,
    PromptContextError,
    build_repository_data,
    render_section,
    serialize_criteria,
    serialize_untrusted_data,
)

_REPOSITORY_TASK_TEMPLATE = """
BACKEND × ENTRY × {analysis_depth} 범위에서 제공된 Repository 하나의 RepositoryAnalysis를 생성한다.
이 Repository에서 완료된 Evidence 깊이는 {completed_levels}이며 이 범위를 넘어 판단하지 않는다.

- Repository 요약은 INTERPRETATION으로 만들고 Evidence 또는 UserClaim을 참조한다.
- 관찰 항목은 OBSERVATION으로 만들고 Evidence를 참조한다.
- 강점 해석은 INTERPRETATION으로 만들고 Evidence 또는 UserClaim을 참조한다.
- 개선 제안은 RECOMMENDATION으로 만들고 Evidence와 우선순위를 포함한다.
- 공개 근거에서 포트폴리오로 설명 가능한 범위와 실제 분석 깊이의 한계를 제시한다.
- UserClaim을 GitHub에서 확인된 사실처럼 표현하지 않는다.
- 미관찰 사실에 관한 Recommendation은 명시적인 BACKEND_DERIVED Evidence가 있을 때만 만든다.
- 점수, 개인 기여율, 사용자 역량, 경력 수준 충족 여부, 취업 또는 합격 가능성을 생성하지 않는다.
- 입력에 없는 기술, 파일 경로, 코드, 호출 관계와 구현 기능을 생성하지 않는다.
- 다른 Repository의 Evidence를 사용하지 않는다.
- 전달된 코드를 실행하지 않는다.
{depth_rules}
- 응답은 Provider가 전달한 RepositoryAnalysis Structured Output Schema를 따른다.
""".strip()

_P0_REPOSITORY_RULES = """
- P0에서는 README, 의존성·설정, 테스트 파일, Docker와 GitHub Actions의 관찰 여부만 판단한다.
- P0만으로 코드 품질, 설계 품질, 테스트 품질 또는 보안 품질을 판단하지 않는다.
""".strip()

_P1_REPOSITORY_RULES = """
- P1에서는 전달된 Commit, PR과 변경 경로에서 관찰되는 활동 소재만 다룬다.
- ACTIVITY_VOLUME_AS_SKILL과 ACTIVITY_VOLUME_AS_CONTRIBUTION을 금지한다.
- 활동 미관찰을 거짓, 미기여 또는 실제 활동 부재로 해석하지 않는다.
- P1만으로 코드, 설계 또는 테스트 품질을 판단하지 않는다.
""".strip()

_P2_REPOSITORY_RULES = """
- P2에서는 제공된 CODE_EVIDENCE snippet에서 직접 보이는 입력 검증, 오류 처리,
  책임과 테스트 사례만 다룬다.
- REPOSITORY_WIDE_GENERALIZATION을 금지하고 snippet을 Repository 전체 품질로 일반화하지 않는다.
- snippet 밖의 코드나 호출 관계를 추정하지 않는다.
""".strip()


def build_repository_prompt(
    context: NormalizedRepositoryContext,
    criteria: CriteriaSet,
) -> str:
    """Build the user prompt for one depth-scoped repository analysis."""

    if context.analysis_depth is not criteria.analysis_depth:
        raise PromptContextError(
            "Repository context and criteria must use the same analysis depth."
        )

    task = _build_repository_task(context)

    return "\n\n".join(
        (
            render_section(CRITERIA_SECTION, serialize_criteria(criteria)),
            render_section(
                REPOSITORY_DATA_SECTION,
                serialize_untrusted_data(build_repository_data(context)),
            ),
            render_section(TASK_SECTION, task),
        )
    )


def _build_repository_task(context: NormalizedRepositoryContext) -> str:
    depth_rules = [_P0_REPOSITORY_RULES]
    if context.analysis_depth in {AnalysisDepth.P1, AnalysisDepth.P2}:
        depth_rules.append(_P1_REPOSITORY_RULES)
    if context.analysis_depth is AnalysisDepth.P2:
        depth_rules.append(_P2_REPOSITORY_RULES)

    return _REPOSITORY_TASK_TEMPLATE.format(
        analysis_depth=context.analysis_depth.value,
        completed_levels=",".join(level.value for level in context.completed_evidence_levels),
        depth_rules="\n".join(depth_rules),
    )
