import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.core.exceptions import ReportPolicyError
from app.criteria import CriteriaSet, Criterion
from app.domain import (
    AnalysisDepth,
    AnalysisItemType,
    GroundedAnalysisItem,
    InternalEvidence,
    InternalEvidenceType,
    NormalizedRepositoryContext,
    RepositoryAnalysis,
)


class PolicyViolationCode(StrEnum):
    UNKNOWN_EVIDENCE_REF = "UNKNOWN_EVIDENCE_REF"
    UNKNOWN_CLAIM_REF = "UNKNOWN_CLAIM_REF"
    CROSS_REPOSITORY_REF = "CROSS_REPOSITORY_REF"
    UNKNOWN_TECHNOLOGY = "UNKNOWN_TECHNOLOGY"
    UNKNOWN_FILE_PATH = "UNKNOWN_FILE_PATH"
    P0_SCOPE_VIOLATION = "P0_SCOPE_VIOLATION"
    USER_ABILITY_ASSERTION = "USER_ABILITY_ASSERTION"
    CONTRIBUTION_ASSERTION = "CONTRIBUTION_ASSERTION"
    NOT_OBSERVED_MISUSE = "NOT_OBSERVED_MISUSE"
    USER_CLAIM_AS_FACT = "USER_CLAIM_AS_FACT"
    MISSING_DERIVED_EVIDENCE = "MISSING_DERIVED_EVIDENCE"
    UNKNOWN_CRITERION = "UNKNOWN_CRITERION"
    CRITERIA_EVIDENCE_MISMATCH = "CRITERIA_EVIDENCE_MISMATCH"
    P1_SCOPE_VIOLATION = "P1_SCOPE_VIOLATION"
    P2_SCOPE_VIOLATION = "P2_SCOPE_VIOLATION"
    REPOSITORY_WIDE_GENERALIZATION = "REPOSITORY_WIDE_GENERALIZATION"


_DEPTH_RANK = {
    AnalysisDepth.P0: 0,
    AnalysisDepth.P1: 1,
    AnalysisDepth.P2: 2,
}

_QUALITY_ASSERTION_PATTERNS = (
    r"(?:코드|구현).{0,20}(?:품질|완성도).{0,20}(?:우수|높|좋|뛰어나|견고)",
    r"(?:설계|아키텍처).{0,30}(?:우수|좋|견고|적절|잘\s*(?:구성|설계))",
    r"(?:테스트).{0,25}(?:품질|커버리지|완성도).{0,20}(?:우수|높|좋|충분|완벽)",
    r"(?:보안|성능|운영\s*안정성).{0,25}(?:우수|높|좋|충분|안정적)",
    r"(?:code|design|architecture|test|security|performance).{0,25}"
    r"(?:quality|coverage).{0,20}(?:good|high|excellent|robust)",
)
_USER_ABILITY_PATTERNS = (
    r"(?:사용자|개발자|지원자).{0,30}(?:실력|역량|숙련도|경력\s*수준).{0,20}"
    r"(?:높|우수|뛰어나|충분|검증|충족)",
    r"(?:실력|역량|숙련도).{0,20}(?:높|우수|뛰어나|검증|충분)",
    r"(?:시니어|중급|주니어).{0,15}(?:수준|역량).{0,15}(?:충족|해당)",
    r"(?:합격|취업)\s*가능성.{0,15}(?:높|낮)",
    r"(?:developer|candidate).{0,25}(?:skill|ability|seniority).{0,20}"
    r"(?:high|excellent|proven|qualified)",
)
_ACTIVITY_CONTRIBUTION_PATTERNS = (
    r"(?:커밋|\bcommit\b|\bPR\b|\bpull request\b|변경량|변경\s*라인|활동량).{0,45}"
    r"(?:기여율|기여도|대부분\s*기여|핵심\s*기여|혼자|전담)",
    r"(?:기여율|기여도).{0,20}(?:\d+\s*%|높|낮|대부분)",
    r"(?:commit|pull request|change volume).{0,40}(?:contribution|ownership)",
)
_DIRECT_IMPLEMENTATION_PATTERNS = (
    r"(?:사용자|개발자|지원자).{0,20}(?:직접|혼자|전적으로).{0,20}(?:구현|작성|담당)",
    r"(?:직접|혼자|전적으로).{0,20}(?:구현|작성)한\s*(?:사실|것이)\s*(?:확인|검증)",
)
_P1_NON_CONTRIBUTION_PATTERNS = (
    r"(?:활동|커밋|\bcommit\b|\bPR\b).{0,30}(?:관찰되지|확인되지|없).{0,25}"
    r"(?:미기여|기여하지|작업하지)",
    r"(?:변경\s*경로|파일\s*변경).{0,30}(?:소유|전담|혼자\s*구현)",
)
_REPOSITORY_GENERALIZATION_PATTERNS = (
    r"(?:저장소|repository|프로젝트).{0,20}(?:전체|전반).{0,35}"
    r"(?:코드\s*품질|아키텍처|설계|테스트\s*품질|커버리지)",
    r"(?:전체|전반적인).{0,20}(?:코드\s*품질|아키텍처|설계|테스트\s*품질|커버리지)"
    r".{0,20}(?:우수|좋|높|견고|충분)",
    r"(?:entire|overall).{0,20}(?:repository|codebase|architecture|test coverage)"
    r".{0,20}(?:good|high|excellent|robust)",
)
_P2_OUT_OF_SCOPE_PATTERNS = (
    r"(?:snippet|코드\s*구간).{0,20}(?:밖|외부).{0,30}(?:구현|호출\s*관계|동작).{0,20}"
    r"(?:확인|입증|검증)",
    r"제공되지\s*않은\s*코드.{0,30}(?:구현|호출\s*관계).{0,20}(?:확인|입증|검증)",
)
_CLAIM_ATTRIBUTION_PATTERNS = (
    r"사용자\s*(?:진술|입력)",
    r"사용자가.{0,20}(?:진술|설명|입력|주장)",
    r"user\s*claim",
    r"self[- ]reported",
)
_CLAIM_AS_FACT_PATTERNS = (
    r"(?:GitHub|깃허브|저장소).{0,20}(?:확인|검증|입증)(?:되었|됐|했다)",
    r"(?:객관적으로|실제로).{0,15}(?:확인|검증|입증)(?:되었|됐|했다)",
    r"(?:실제|직접)\s*구현.{0,15}(?:확인|검증|입증)(?:되었|됐|했다)",
)
_NOT_OBSERVED_ABSENCE_PATTERNS = (
    r"(?:실제로|완전히|전혀)?\s*(?:존재하지\s*않|없(?:습니다|다)|구현하지\s*않)",
    r"(?:거짓|미기여|기여하지\s*않)",
)
_OBSERVATION_SCOPE_PATTERNS = (
    r"(?:수집|분석|공개\s*근거)\s*범위",
    r"(?:관찰|확인)되지\s*않",
    r"not\s+observed",
)
_MISSING_RECOMMENDATION_PATTERNS = (
    r"(?:누락|미관찰|확인되지\s*않|존재하지\s*않|없(?:습니다|다))",
    r"(?:추가|보완|작성|도입|구성)(?:하|해\s*주)",
)

_MISSING_EVIDENCE_CRITERIA = frozenset(
    {
        "README_READINESS",
        "TEST_PRESENCE",
        "DOCKER_CONFIGURATION",
        "GITHUB_ACTIONS_CONFIGURATION",
    }
)


@dataclass(frozen=True, slots=True)
class PolicyViolation:
    code: PolicyViolationCode
    message: str
    field_path: str | None = None

    def __post_init__(self) -> None:
        message = self.message.strip()
        if not message:
            raise ValueError("Policy violation message must not be blank")
        object.__setattr__(self, "message", message)

        if self.field_path is None:
            return

        field_path = self.field_path.strip()
        if not field_path:
            raise ValueError("Policy violation field_path must not be blank")
        object.__setattr__(self, "field_path", field_path)


class RepositoryPolicyValidator:
    """Validate repository-scoped references and generated-content policy."""

    def validate_references(
        self,
        analysis: RepositoryAnalysis,
        expected_context: NormalizedRepositoryContext,
        portfolio_contexts: Sequence[NormalizedRepositoryContext],
    ) -> None:
        expected_repository = expected_context.repository_full_name
        evidence_owners = {
            evidence.evidence_id: context.repository_full_name
            for context in portfolio_contexts
            for evidence in context.evidence
        }
        claim_owners = {
            claim.claim_id: context.repository_full_name
            for context in portfolio_contexts
            for claim in context.user_claims
        }

        violations: list[PolicyViolation] = []
        if analysis.repository_full_name != expected_repository:
            violations.append(
                PolicyViolation(
                    code=PolicyViolationCode.CROSS_REPOSITORY_REF,
                    message="Repository analysis does not match the expected repository.",
                    field_path="repository_full_name",
                )
            )

        for field_path, item in self._iter_analysis_items(analysis):
            violations.extend(
                self._find_item_reference_violations(
                    item=item,
                    field_path=field_path,
                    expected_repository=expected_repository,
                    evidence_owners=evidence_owners,
                    claim_owners=claim_owners,
                )
            )

        if violations:
            raise ReportPolicyError(violations)

    def validate_content(
        self,
        analysis: RepositoryAnalysis,
        context: NormalizedRepositoryContext,
        criteria: CriteriaSet,
    ) -> None:
        """Reject ungrounded metadata and depth-incompatible generated claims."""

        criteria_by_key = {criterion.key: criterion for criterion in criteria.criteria}
        evidence_by_id = {evidence.evidence_id: evidence for evidence in context.evidence}
        allowed_technologies = {name.casefold() for name in context.technology_names}
        allowed_paths = {
            path
            for evidence in context.evidence
            for path in (*evidence.source_paths, evidence.path)
            if path is not None
        }

        violations: list[PolicyViolation] = []
        for field_path, item in self._iter_analysis_items(analysis):
            applied_criteria, metadata_violations = self._validate_item_metadata(
                item=item,
                field_path=field_path,
                context=context,
                criteria_by_key=criteria_by_key,
                evidence_by_id=evidence_by_id,
                allowed_technologies=allowed_technologies,
                allowed_paths=allowed_paths,
            )
            violations.extend(metadata_violations)
            violations.extend(
                self._find_content_violations(
                    item=item,
                    field_path=field_path,
                    context=context,
                    applied_criteria=applied_criteria,
                    evidence_by_id=evidence_by_id,
                )
            )

        if violations:
            raise ReportPolicyError(violations)

    def _validate_item_metadata(
        self,
        *,
        item: GroundedAnalysisItem,
        field_path: str,
        context: NormalizedRepositoryContext,
        criteria_by_key: dict[str, Criterion],
        evidence_by_id: dict[str, InternalEvidence],
        allowed_technologies: set[str],
        allowed_paths: set[str],
    ) -> tuple[tuple[Criterion, ...], tuple[PolicyViolation, ...]]:
        violations: list[PolicyViolation] = []
        applied_criteria: list[Criterion] = []

        for index, criterion_key in enumerate(item.criterion_keys):
            criterion = criteria_by_key.get(criterion_key)
            criterion_path = f"{field_path}.criterion_keys[{index}]"
            if criterion is None:
                violations.append(
                    PolicyViolation(
                        code=PolicyViolationCode.UNKNOWN_CRITERION,
                        message="Analysis item uses a criterion outside the supplied criteria set.",
                        field_path=criterion_path,
                    )
                )
                continue
            applied_criteria.append(criterion)
            if _DEPTH_RANK[criterion.analysis_depth] > _DEPTH_RANK[context.analysis_depth]:
                violations.append(
                    PolicyViolation(
                        code=_scope_violation_code(context.analysis_depth),
                        message="Analysis item uses a criterion above the repository depth.",
                        field_path=criterion_path,
                    )
                )

        eligible_criteria = tuple(
            criterion
            for criterion in applied_criteria
            if _DEPTH_RANK[criterion.analysis_depth] <= _DEPTH_RANK[context.analysis_depth]
        )
        for index, evidence_ref in enumerate(item.evidence_refs):
            evidence = evidence_by_id.get(evidence_ref)
            if evidence is None:
                continue
            matches_criterion = any(
                evidence.evidence_type in criterion.allowed_evidence_types
                and evidence.analysis_depth is criterion.analysis_depth
                for criterion in eligible_criteria
            )
            if not matches_criterion:
                violations.append(
                    PolicyViolation(
                        code=PolicyViolationCode.CRITERIA_EVIDENCE_MISMATCH,
                        message="Referenced evidence is not allowed by the applied criteria.",
                        field_path=f"{field_path}.evidence_refs[{index}]",
                    )
                )

        if item.claim_refs and not any(
            criterion.allow_user_claims for criterion in eligible_criteria
        ):
            for index, _claim_ref in enumerate(item.claim_refs):
                violations.append(
                    PolicyViolation(
                        code=PolicyViolationCode.CRITERIA_EVIDENCE_MISMATCH,
                        message="Applied criteria do not allow user claims.",
                        field_path=f"{field_path}.claim_refs[{index}]",
                    )
                )

        for index, technology_name in enumerate(item.technology_names):
            if technology_name.casefold() not in allowed_technologies:
                violations.append(
                    PolicyViolation(
                        code=PolicyViolationCode.UNKNOWN_TECHNOLOGY,
                        message="Analysis item uses a technology outside the repository context.",
                        field_path=f"{field_path}.technology_names[{index}]",
                    )
                )

        for index, file_path in enumerate(item.file_paths):
            if file_path not in allowed_paths:
                violations.append(
                    PolicyViolation(
                        code=PolicyViolationCode.UNKNOWN_FILE_PATH,
                        message="Analysis item uses a file path outside the repository context.",
                        field_path=f"{field_path}.file_paths[{index}]",
                    )
                )

        return tuple(applied_criteria), tuple(violations)

    def _find_content_violations(
        self,
        *,
        item: GroundedAnalysisItem,
        field_path: str,
        context: NormalizedRepositoryContext,
        applied_criteria: tuple[Criterion, ...],
        evidence_by_id: dict[str, InternalEvidence],
    ) -> tuple[PolicyViolation, ...]:
        violations: list[PolicyViolation] = []
        content = item.content
        referenced_evidence = tuple(
            evidence_by_id[reference]
            for reference in item.evidence_refs
            if reference in evidence_by_id
        )
        claim_attributed = _matches_any(content, _CLAIM_ATTRIBUTION_PATTERNS)
        item_depth = _effective_item_depth(applied_criteria, context.analysis_depth)

        if item_depth is AnalysisDepth.P0 and _matches_any(content, _QUALITY_ASSERTION_PATTERNS):
            violations.append(
                _content_violation(
                    PolicyViolationCode.P0_SCOPE_VIOLATION,
                    "P0 item makes a quality judgment outside structural evidence.",
                    field_path,
                )
            )
        if item_depth is AnalysisDepth.P1 and _matches_any(content, _QUALITY_ASSERTION_PATTERNS):
            violations.append(
                _content_violation(
                    PolicyViolationCode.P1_SCOPE_VIOLATION,
                    "P1 item makes a code, design, or test quality judgment.",
                    field_path,
                )
            )
        if item_depth is AnalysisDepth.P2:
            if _matches_any(content, _REPOSITORY_GENERALIZATION_PATTERNS):
                violations.append(
                    _content_violation(
                        PolicyViolationCode.REPOSITORY_WIDE_GENERALIZATION,
                        "P2 snippet finding is generalized to the whole repository.",
                        field_path,
                    )
                )
            if _matches_any(content, _P2_OUT_OF_SCOPE_PATTERNS):
                violations.append(
                    _content_violation(
                        PolicyViolationCode.P2_SCOPE_VIOLATION,
                        "P2 item asserts behavior outside the supplied snippet.",
                        field_path,
                    )
                )

        if _matches_any(content, _USER_ABILITY_PATTERNS):
            violations.append(
                _content_violation(
                    PolicyViolationCode.USER_ABILITY_ASSERTION,
                    "Analysis item asserts user ability or career outcome.",
                    field_path,
                )
            )

        if _matches_any(content, _ACTIVITY_CONTRIBUTION_PATTERNS) or (
            not claim_attributed and _matches_any(content, _DIRECT_IMPLEMENTATION_PATTERNS)
        ):
            violations.append(
                _content_violation(
                    PolicyViolationCode.CONTRIBUTION_ASSERTION,
                    "Analysis item asserts personal contribution or ownership.",
                    field_path,
                )
            )

        if item_depth in {AnalysisDepth.P1, AnalysisDepth.P2} and _matches_any(
            content, _P1_NON_CONTRIBUTION_PATTERNS
        ):
            violations.append(
                _content_violation(
                    PolicyViolationCode.CONTRIBUTION_ASSERTION,
                    "Activity evidence is interpreted as contribution or non-contribution.",
                    field_path,
                )
            )

        if item.claim_refs and (
            _matches_any(content, _CLAIM_AS_FACT_PATTERNS)
            or (not item.evidence_refs and not claim_attributed)
        ):
            violations.append(
                _content_violation(
                    PolicyViolationCode.USER_CLAIM_AS_FACT,
                    "User claim is presented without claim attribution.",
                    field_path,
                )
            )

        if (
            _contains_not_observed_evidence(referenced_evidence)
            and _matches_any(content, _NOT_OBSERVED_ABSENCE_PATTERNS)
            and not _matches_any(content, _OBSERVATION_SCOPE_PATTERNS)
        ):
            violations.append(
                _content_violation(
                    PolicyViolationCode.NOT_OBSERVED_MISUSE,
                    "Not-observed evidence is presented as actual absence or non-contribution.",
                    field_path,
                )
            )

        if item.item_type is AnalysisItemType.RECOMMENDATION and _matches_any(
            content, _MISSING_RECOMMENDATION_PATTERNS
        ):
            for criterion in applied_criteria:
                if criterion.key not in _MISSING_EVIDENCE_CRITERIA:
                    continue
                if not _has_matching_missing_evidence(
                    criterion.key,
                    referenced_evidence,
                ):
                    violations.append(
                        _content_violation(
                            PolicyViolationCode.MISSING_DERIVED_EVIDENCE,
                            "Missing-item recommendation lacks explicit derived evidence.",
                            field_path,
                        )
                    )

        return tuple(violations)

    @staticmethod
    def _iter_analysis_items(
        analysis: RepositoryAnalysis,
    ) -> tuple[tuple[str, GroundedAnalysisItem], ...]:
        indexed_items: list[tuple[str, GroundedAnalysisItem]] = [("summary", analysis.summary)]
        collections = (
            ("observations", analysis.observations),
            ("strengths", analysis.strengths),
            ("recommendations", analysis.recommendations),
        )
        for collection_name, items in collections:
            indexed_items.extend(
                (f"{collection_name}[{index}]", item) for index, item in enumerate(items)
            )
        return tuple(indexed_items)

    @staticmethod
    def _find_item_reference_violations(
        *,
        item: GroundedAnalysisItem,
        field_path: str,
        expected_repository: str,
        evidence_owners: dict[str, str],
        claim_owners: dict[str, str],
    ) -> tuple[PolicyViolation, ...]:
        violations: list[PolicyViolation] = []

        for index, evidence_ref in enumerate(item.evidence_refs):
            owner = evidence_owners.get(evidence_ref)
            reference_path = f"{field_path}.evidence_refs[{index}]"
            if owner is None:
                violations.append(
                    PolicyViolation(
                        code=PolicyViolationCode.UNKNOWN_EVIDENCE_REF,
                        message="Analysis item references unknown evidence.",
                        field_path=reference_path,
                    )
                )
            elif owner != expected_repository:
                violations.append(
                    PolicyViolation(
                        code=PolicyViolationCode.CROSS_REPOSITORY_REF,
                        message="Analysis item references evidence from another repository.",
                        field_path=reference_path,
                    )
                )

        for index, claim_ref in enumerate(item.claim_refs):
            owner = claim_owners.get(claim_ref)
            reference_path = f"{field_path}.claim_refs[{index}]"
            if owner is None:
                violations.append(
                    PolicyViolation(
                        code=PolicyViolationCode.UNKNOWN_CLAIM_REF,
                        message="Analysis item references an unknown user claim.",
                        field_path=reference_path,
                    )
                )
            elif owner != expected_repository:
                violations.append(
                    PolicyViolation(
                        code=PolicyViolationCode.CROSS_REPOSITORY_REF,
                        message="Analysis item references a user claim from another repository.",
                        field_path=reference_path,
                    )
                )

        return tuple(violations)


def _scope_violation_code(depth: AnalysisDepth) -> PolicyViolationCode:
    if depth is AnalysisDepth.P0:
        return PolicyViolationCode.P0_SCOPE_VIOLATION
    if depth is AnalysisDepth.P1:
        return PolicyViolationCode.P1_SCOPE_VIOLATION
    return PolicyViolationCode.P2_SCOPE_VIOLATION


def _effective_item_depth(
    criteria: tuple[Criterion, ...],
    fallback: AnalysisDepth,
) -> AnalysisDepth:
    if not criteria:
        return fallback
    return max((criterion.analysis_depth for criterion in criteria), key=_DEPTH_RANK.__getitem__)


def _content_violation(
    code: PolicyViolationCode,
    message: str,
    item_path: str,
) -> PolicyViolation:
    return PolicyViolation(code=code, message=message, field_path=f"{item_path}.content")


def _matches_any(content: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, content, flags=re.IGNORECASE) for pattern in patterns)


def _contains_not_observed_evidence(evidence: tuple[InternalEvidence, ...]) -> bool:
    for item in evidence:
        key = item.key.upper()
        if "NOT_OBSERVED" in key or "MISSING" in key:
            return True
        if item.evidence_type is InternalEvidenceType.BACKEND_DERIVED and (
            _project_structure_value(item.summary, "testFileCount", "0")
            or _project_structure_value(item.summary, "hasDocker", "false")
            or _project_structure_value(item.summary, "hasCi", "false")
        ):
            return True
    return False


def _has_matching_missing_evidence(
    criterion_key: str,
    evidence: tuple[InternalEvidence, ...],
) -> bool:
    derived = tuple(
        item for item in evidence if item.evidence_type is InternalEvidenceType.BACKEND_DERIVED
    )
    if criterion_key == "README_READINESS":
        return any(
            item.key in {"README_SECTION_MISSING", "README_NOT_OBSERVED"} for item in derived
        )
    if criterion_key == "TEST_PRESENCE":
        return any(
            item.key == "TEST_NOT_OBSERVED"
            or (
                item.key == "PROJECT_STRUCTURE"
                and _project_structure_value(item.summary, "testFileCount", "0")
            )
            for item in derived
        )
    if criterion_key == "DOCKER_CONFIGURATION":
        return any(
            item.key == "DEPLOYMENT_CONFIG_NOT_OBSERVED"
            or (
                item.key == "PROJECT_STRUCTURE"
                and _project_structure_value(item.summary, "hasDocker", "false")
            )
            for item in derived
        )
    if criterion_key == "GITHUB_ACTIONS_CONFIGURATION":
        return any(
            item.key == "GITHUB_ACTIONS_NOT_OBSERVED"
            or (
                item.key == "PROJECT_STRUCTURE"
                and _project_structure_value(item.summary, "hasCi", "false")
            )
            for item in derived
        )
    return False


def _project_structure_value(summary: str, field: str, value: str) -> bool:
    return bool(
        re.search(
            rf"(?:^|[\s,;]){re.escape(field)}\s*=\s*{re.escape(value)}(?:$|[\s,;])",
            summary,
            flags=re.IGNORECASE,
        )
    )


__all__ = ["PolicyViolation", "PolicyViolationCode", "RepositoryPolicyValidator"]
