from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.criteria.models import CriteriaSet
from app.domain import NormalizedRepositoryContext

if TYPE_CHECKING:
    from app.services.criterion_context_service import CriterionEvidenceContext

CRITERIA_SECTION = "CRITERIA"
REPOSITORY_DATA_SECTION = "UNTRUSTED_REPOSITORY_DATA"
PRIOR_ANALYSIS_SECTION = "UNTRUSTED_PRIOR_ANALYSIS_DATA"
TASK_SECTION = "TASK"

_RESERVED_SECTION_NAMES = (
    CRITERIA_SECTION,
    REPOSITORY_DATA_SECTION,
    PRIOR_ANALYSIS_SECTION,
    TASK_SECTION,
)
_RESERVED_SECTION_MARKERS = tuple(
    f"[{section_name}_{boundary}]"
    for section_name in _RESERVED_SECTION_NAMES
    for boundary in ("BEGIN", "END")
)


class PromptContextError(ValueError):
    """Raised when data cannot form a complete and deterministic prompt context."""


def build_user_claim_rules(criteria: CriteriaSet) -> str:
    """Describe exactly when generated items may reference untrusted user claims."""

    claim_criteria = tuple(
        criterion.key for criterion in criteria.criteria if criterion.allow_user_claims
    )
    if not claim_criteria:
        return (
            "- 현재 Criteria는 UserClaim 참조를 허용하지 않는다. UserClaim을 생성 결과의 "
            "근거로 사용하지 않고 모든 claim_refs를 빈 배열로 반환한다."
        )

    allowed_keys = ", ".join(claim_criteria)
    return (
        "- UserClaim은 allow_user_claims=true인 Criterion Context에서만 사용할 수 있다. "
        f"현재 이에 해당하는 Criteria는 {allowed_keys}이다. UserClaim을 참조하는 항목은 "
        "claim_refs를 허용하는 criterion_context_refs와 함께 반환하고 검증된 GitHub "
        "사실처럼 표현하지 않는다."
    )


def serialize_criteria(criteria: CriteriaSet) -> str:
    """Serialize trusted, locally validated criteria as canonical JSON."""

    return _serialize_json(criteria)


def serialize_untrusted_data(
    data: BaseModel | Sequence[BaseModel] | Mapping[str, object],
) -> str:
    """Serialize untrusted data and neutralize reserved prompt section markers."""

    return _escape_reserved_section_markers(_serialize_json(data))


def render_section(name: str, content: str) -> str:
    """Wrap one prompt section with explicit begin and end markers."""

    if not name or not content:
        raise PromptContextError("Prompt section name and content must not be empty.")
    return f"[{name}_BEGIN]\n{content}\n[{name}_END]"


def build_evidence_criterion_rules() -> str:
    """Describe the service-owned Criterion Context contract used for generation."""

    return "\n".join(
        (
            "- 각 생성 항목은 인용한 모든 evidence_refs와 claim_refs를 허용하는 "
            "criterionContexts의 context_id를 criterion_context_refs에 반환한다.",
            "- criterionKey를 생성하거나 수정하지 않는다. 서비스가 검증된 "
            "criterion_context_refs로부터 criterionKey를 주입한다.",
            "- 선택한 각 Criterion Context는 생성 항목이 실제 인용한 Evidence 또는 "
            "UserClaim을 하나 이상 포함해야 한다.",
            "- 허용된 Criterion Context가 없는 Evidence 또는 UserClaim은 인용하지 않는다.",
            "- analysisDepth와 evidenceType만으로 Criterion을 임의 선택하지 않는다.",
        )
    )


def build_repository_data(
    context: NormalizedRepositoryContext,
    criteria: CriteriaSet,
    criterion_contexts: Sequence[CriterionEvidenceContext] | None = None,
    *,
    include_criterion_contexts: bool = True,
) -> dict[str, object]:
    """Keep repository metadata, depth-scoped evidence, and user claims separate."""

    evidence_by_depth = {
        depth.value: tuple(
            evidence for evidence in context.evidence if evidence.analysis_depth is depth
        )
        for depth in context.completed_evidence_levels
    }

    data: dict[str, object] = {
        "repository": {
            "repository_id": context.repository_id,
            "repository_full_name": context.repository_full_name,
            "description": context.description,
            "analysis_depth": context.analysis_depth,
            "completed_evidence_levels": context.completed_evidence_levels,
            "snapshot_hash_algorithm": context.snapshot_hash_algorithm,
            "snapshot_sha": context.snapshot_sha,
            "technology_names": context.technology_names,
        },
        "evidence_by_depth": evidence_by_depth,
        "user_claims": context.user_claims,
    }
    if include_criterion_contexts:
        resolved_contexts = _resolve_criterion_contexts(
            (context,),
            criteria,
            criterion_contexts,
        )
        data["criterionContexts"] = build_criterion_context_data(resolved_contexts)
    return data


def build_criterion_context_data(
    contexts: Sequence[CriterionEvidenceContext],
) -> tuple[dict[str, object], ...]:
    """Serialize service-owned Criterion Contexts without changing their scope."""

    return tuple(
        {
            "context_id": item.context_id,
            "criterion_key": item.criterion_key,
            "analysis_depth": item.analysis_depth,
            "title": item.title,
            "description": item.description,
            "eligible_evidence_refs": item.eligible_evidence_refs,
            "eligible_claim_refs": item.eligible_claim_refs,
        }
        for item in contexts
    )


def _resolve_criterion_contexts(
    repositories: Sequence[NormalizedRepositoryContext],
    criteria: CriteriaSet,
    criterion_contexts: Sequence[CriterionEvidenceContext] | None,
) -> tuple[CriterionEvidenceContext, ...]:
    if criterion_contexts is None:
        from app.services.criterion_context_service import CriterionContextService

        return CriterionContextService().build(repositories, criteria)

    contexts = tuple(criterion_contexts)
    if not contexts:
        raise PromptContextError("Prompt requires at least one Criterion Context.")
    allowed_keys = {criterion.key for criterion in criteria.criteria}
    if any(context.criterion_key not in allowed_keys for context in contexts):
        raise PromptContextError("Criterion Context contains a key outside the Criteria set.")
    return contexts


def _serialize_json(value: object) -> str:
    try:
        json_value = _to_json_value(value)
        return json.dumps(
            json_value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise PromptContextError("Prompt context could not be serialized as JSON.") from exc


def _escape_reserved_section_markers(serialized_json: str) -> str:
    """Escape exact structural markers while preserving valid, reversible JSON."""

    escaped_json = serialized_json
    for marker in _RESERVED_SECTION_MARKERS:
        escaped_marker = marker.replace("[", r"\u005b").replace("]", r"\u005d")
        escaped_json = escaped_json.replace(marker, escaped_marker)
    return escaped_json


def _to_json_value(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_to_json_value(item) for item in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise TypeError(f"unsupported prompt context value: {type(value).__name__}")
