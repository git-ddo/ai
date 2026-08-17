from app.criteria.models import CriteriaSet
from app.domain import NormalizedRepositoryContext
from app.prompts.context import (
    CRITERIA_SECTION,
    REPOSITORY_DATA_SECTION,
    TASK_SECTION,
    build_repository_data,
    render_section,
    serialize_criteria,
    serialize_untrusted_data,
)

_REPOSITORY_TASK = """
BACKEND × ENTRY × P0 범위에서 제공된 Repository 하나의 RepositoryAnalysis를 생성한다.

- Repository 요약은 INTERPRETATION으로 만들고 Evidence 또는 UserClaim을 참조한다.
- 관찰 항목은 OBSERVATION으로 만들고 Evidence를 참조한다.
- 강점 해석은 INTERPRETATION으로 만들고 Evidence 또는 UserClaim을 참조한다.
- 개선 제안은 RECOMMENDATION으로 만들고 Evidence와 우선순위를 포함한다.
- 공개 근거에서 포트폴리오로 설명 가능한 범위와 P0 분석 한계를 제시한다.
- UserClaim을 GitHub에서 확인된 사실처럼 표현하지 않는다.
- 미관찰 사실에 관한 Recommendation은 명시적인 BACKEND_DERIVED Evidence가 있을 때만 만든다.
- 코드 품질, 설계 품질, 테스트 품질, 보안 품질을 판단하지 않는다.
- 점수, 개인 기여율, 사용자 역량, 경력 수준 충족 여부, 취업 또는 합격 가능성을 생성하지 않는다.
- 입력에 없는 기술, 파일 경로와 구현 기능을 생성하지 않는다.
- 응답은 Provider가 전달한 RepositoryAnalysis Structured Output Schema를 따른다.
""".strip()


def build_repository_prompt(
    context: NormalizedRepositoryContext,
    criteria: CriteriaSet,
) -> str:
    """Build the user prompt for one grounded P0 repository analysis."""

    return "\n\n".join(
        (
            render_section(CRITERIA_SECTION, serialize_criteria(criteria)),
            render_section(
                REPOSITORY_DATA_SECTION,
                serialize_untrusted_data(build_repository_data(context)),
            ),
            render_section(TASK_SECTION, _REPOSITORY_TASK),
        )
    )
