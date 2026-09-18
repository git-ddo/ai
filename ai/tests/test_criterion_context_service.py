import pytest

from app.criteria import CriteriaLoader
from app.domain import AnalysisDepth, CodeObservationType, InternalEvidenceType
from app.services import CriterionContextService, CriterionEvidenceContext
from tests.test_repository_service import make_context


def _by_key(
    contexts: tuple[CriterionEvidenceContext, ...],
) -> dict[str, CriterionEvidenceContext]:
    return {context.criterion_key: context for context in contexts}


def test_builds_deterministic_context_ids_in_criteria_order() -> None:
    repository = make_context(AnalysisDepth.P0)

    contexts = CriterionContextService().build(
        (repository,), CriteriaLoader().load("BACKEND", "P0")
    )

    assert [item.context_id for item in contexts] == ["ctx_002"]
    assert contexts[0].criterion_key == "TECH_STACK_EVIDENCE"
    assert contexts[0].eligible_evidence_refs == (repository.evidence[0].evidence_id,)


def test_narrows_p2_code_evidence_with_structured_observation_types() -> None:
    repository = make_context(AnalysisDepth.P2)
    code = repository.evidence[-1].model_copy(
        update={
            "code_observation_types": (
                CodeObservationType.SNIPPET_SCOPE,
                CodeObservationType.INPUT_VALIDATION,
                CodeObservationType.RESPONSIBILITY,
            )
        }
    )
    repository = repository.model_copy(update={"evidence": (*repository.evidence[:-1], code)})

    contexts = CriterionContextService().build(
        (repository,), CriteriaLoader().load("BACKEND", "P2")
    )
    by_key = _by_key(contexts)
    evidence_id = code.evidence_id

    assert evidence_id in by_key["SNIPPET_SCOPE"].eligible_evidence_refs
    assert evidence_id in by_key["INPUT_VALIDATION_OBSERVATION"].eligible_evidence_refs
    assert evidence_id in by_key["RESPONSIBILITY_OBSERVATION"].eligible_evidence_refs
    assert "TEST_CASE_OBSERVATION" not in by_key
    assert "ERROR_HANDLING_OBSERVATION" not in by_key


def test_exposes_claims_only_to_claim_compatible_context() -> None:
    repository = make_context(
        AnalysisDepth.P1,
        claim_statement="서비스 API 구현을 담당했습니다.",
    )

    contexts = CriterionContextService().build(
        (repository,), CriteriaLoader().load("BACKEND", "P1")
    )
    by_key = _by_key(contexts)

    assert by_key["CLAIM_ACTIVITY_LINK"].eligible_claim_refs == (
        repository.user_claims[0].claim_id,
    )
    assert by_key["ACTIVITY_SCOPE"].eligible_claim_refs == ()


@pytest.mark.parametrize(
    ("depth", "evidence_index", "fact_key", "evidence_type", "expected_criterion"),
    [
        (
            AnalysisDepth.P0,
            0,
            "README_SECTIONS_OBSERVED",
            InternalEvidenceType.GITHUB_STATIC,
            "README_READINESS",
        ),
        (
            AnalysisDepth.P0,
            0,
            "TEST_FILES_OBSERVED",
            InternalEvidenceType.GITHUB_STATIC,
            "TEST_PRESENCE",
        ),
        (
            AnalysisDepth.P0,
            0,
            "DOCKER_COMPOSE_OBSERVED",
            InternalEvidenceType.GITHUB_STATIC,
            "DOCKER_CONFIGURATION",
        ),
        (
            AnalysisDepth.P0,
            0,
            "GITHUB_ACTIONS_NOT_OBSERVED",
            InternalEvidenceType.BACKEND_DERIVED,
            "GITHUB_ACTIONS_CONFIGURATION",
        ),
        (
            AnalysisDepth.P0,
            0,
            "GITHUB_ACTIONS_WORKFLOW_OBSERVED",
            InternalEvidenceType.GITHUB_STATIC,
            "GITHUB_ACTIONS_CONFIGURATION",
        ),
        (
            AnalysisDepth.P1,
            1,
            "COMMIT_ACTIVITY_OBSERVED",
            InternalEvidenceType.GITHUB_ACTIVITY,
            "ACTIVITY_SCOPE",
        ),
    ],
)
def test_narrows_actual_backend_fact_keys_to_one_criterion(
    depth: AnalysisDepth,
    evidence_index: int,
    fact_key: str,
    evidence_type: InternalEvidenceType,
    expected_criterion: str,
) -> None:
    repository = make_context(depth)
    target = repository.evidence[evidence_index].model_copy(
        update={
            "key": fact_key,
            "evidence_type": evidence_type,
        }
    )
    evidence = list(repository.evidence)
    evidence[evidence_index] = target
    repository = repository.model_copy(update={"evidence": tuple(evidence)})

    contexts = CriterionContextService().build(
        (repository,), CriteriaLoader().load("BACKEND", depth.value)
    )
    matched_criteria = {
        context.criterion_key
        for context in contexts
        if target.evidence_id in context.eligible_evidence_refs
    }

    assert matched_criteria == {expected_criterion}
