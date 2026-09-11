import json
from collections.abc import Mapping, Sequence

from pydantic import BaseModel

from app.criteria.models import CriteriaSet
from app.domain import NormalizedRepositoryContext

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
        "- UserClaim은 allow_user_claims=true인 Criteria에만 사용할 수 있다. "
        f"현재 허용 Criteria는 {allowed_keys}이다. UserClaim을 참조하는 항목은 허용 Criteria "
        "key와 claim_refs를 함께 포함하고 검증된 GitHub 사실처럼 표현하지 않는다."
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


def build_repository_data(context: NormalizedRepositoryContext) -> dict[str, object]:
    """Keep repository metadata, depth-scoped evidence, and user claims separate."""

    evidence_by_depth = {
        depth.value: tuple(
            evidence for evidence in context.evidence if evidence.analysis_depth is depth
        )
        for depth in context.completed_evidence_levels
    }

    return {
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
