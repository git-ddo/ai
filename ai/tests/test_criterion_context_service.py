from app.criteria import CriteriaLoader
from app.domain import AnalysisDepth, CodeObservationType
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
