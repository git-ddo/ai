import json

import pytest

from app.core.exceptions import ReportPolicyError
from app.criteria import CriteriaLoader
from app.domain import (
    AnalysisDepth,
    AnalysisItemType,
    EvidenceConfidence,
    GroundedAnalysisDraft,
    InterviewQuestionBatchDraft,
    InterviewQuestionDraft,
    PortfolioStatementBatchDraft,
    PortfolioStatementDraft,
    PortfolioStatementType,
    PortfolioSynthesisDraft,
    RepositoryAnalysisDraft,
    RepresentativeProject,
)
from app.services import CriterionAssignmentService, CriterionContextService
from app.validators import PolicyViolationCode
from tests.test_repository_service import make_context


def _context_id_by_key(depth: AnalysisDepth) -> tuple[object, dict[str, str]]:
    repository = make_context(depth, claim_statement="인증 API를 담당했습니다.")
    criteria = CriteriaLoader().load("BACKEND", depth.value)
    contexts = CriterionContextService().build((repository,), criteria)
    return repository, {context.criterion_key: context.context_id for context in contexts}


def _analysis_draft(
    repository_name: str,
    evidence_ref: str,
    context_refs: tuple[str, ...],
) -> RepositoryAnalysisDraft:
    return RepositoryAnalysisDraft(
        repository_full_name=repository_name,
        summary=GroundedAnalysisDraft(
            item_type=AnalysisItemType.INTERPRETATION,
            content="공개 근거 범위에서 기술 구성을 설명할 수 있습니다.",
            confidence=EvidenceConfidence.HIGH,
            evidence_refs=(evidence_ref,),
            criterion_context_refs=context_refs,
        ),
    )


@pytest.mark.parametrize(
    "model",
    (
        RepositoryAnalysisDraft,
        PortfolioSynthesisDraft,
        InterviewQuestionBatchDraft,
        PortfolioStatementBatchDraft,
    ),
)
def test_provider_schemas_expose_context_refs_without_criterion_keys(model: type) -> None:
    schema = json.dumps(model.model_json_schema(), sort_keys=True)

    assert "criterion_context_refs" in schema
    assert "criterion_keys" not in schema


def test_assigns_context_owned_key_to_repository_draft() -> None:
    repository, context_ids = _context_id_by_key(AnalysisDepth.P0)
    criteria = CriteriaLoader().load("BACKEND", "P0")
    contexts = CriterionContextService().build((repository,), criteria)
    draft = _analysis_draft(
        repository.repository_full_name,
        repository.evidence[0].evidence_id,
        (context_ids["TECH_STACK_EVIDENCE"],),
    )

    analysis = CriterionAssignmentService().assign_repository(draft, contexts)

    assert analysis.summary.criterion_keys == ("TECH_STACK_EVIDENCE",)
    assert "criterion_context_refs" not in analysis.summary.model_dump()


def test_rejects_evidence_outside_selected_context_without_rewriting() -> None:
    repository, context_ids = _context_id_by_key(AnalysisDepth.P1)
    criteria = CriteriaLoader().load("BACKEND", "P1")
    contexts = CriterionContextService().build((repository,), criteria)
    draft = _analysis_draft(
        repository.repository_full_name,
        repository.evidence[0].evidence_id,
        (context_ids["ACTIVITY_SCOPE"],),
    )

    with pytest.raises(ReportPolicyError) as exc_info:
        CriterionAssignmentService().assign_repository(draft, contexts)

    assert exc_info.value.violations[0].code is (
        PolicyViolationCode.CRITERION_CONTEXT_EVIDENCE_MISMATCH
    )
    assert draft.summary.criterion_context_refs == (context_ids["ACTIVITY_SCOPE"],)


def test_rejects_unknown_and_unused_contexts_explicitly() -> None:
    repository, context_ids = _context_id_by_key(AnalysisDepth.P1)
    criteria = CriteriaLoader().load("BACKEND", "P1")
    contexts = CriterionContextService().build((repository,), criteria)

    unknown = _analysis_draft(
        repository.repository_full_name,
        repository.evidence[0].evidence_id,
        ("ctx_999",),
    )
    with pytest.raises(ReportPolicyError) as unknown_error:
        CriterionAssignmentService().assign_repository(unknown, contexts)
    assert unknown_error.value.violations[0].code is (PolicyViolationCode.UNKNOWN_CRITERION_CONTEXT)

    unused = _analysis_draft(
        repository.repository_full_name,
        repository.evidence[0].evidence_id,
        (
            context_ids["TECH_STACK_EVIDENCE"],
            context_ids["ACTIVITY_SCOPE"],
        ),
    )
    with pytest.raises(ReportPolicyError) as unused_error:
        CriterionAssignmentService().assign_repository(unused, contexts)
    assert unused_error.value.violations[0].code is (PolicyViolationCode.UNUSED_CRITERION_CONTEXT)


def test_assigns_keys_for_all_provider_output_shapes() -> None:
    repository, context_ids = _context_id_by_key(AnalysisDepth.P0)
    criteria = CriteriaLoader().load("BACKEND", "P0")
    contexts = CriterionContextService().build((repository,), criteria)
    context_ref = context_ids["TECH_STACK_EVIDENCE"]
    evidence_ref = repository.evidence[0].evidence_id
    grounded = GroundedAnalysisDraft(
        item_type=AnalysisItemType.INTERPRETATION,
        content="공개 기술 근거를 설명할 수 있습니다.",
        confidence=EvidenceConfidence.HIGH,
        evidence_refs=(evidence_ref,),
        criterion_context_refs=(context_ref,),
    )
    job_appeal = grounded.model_copy(update={"item_type": AnalysisItemType.JOB_APPEAL})
    assignment = CriterionAssignmentService()

    synthesis = assignment.assign_portfolio(
        PortfolioSynthesisDraft(
            overall_summary=grounded,
            representative_projects=(
                RepresentativeProject(
                    repository_full_name=repository.repository_full_name,
                    reason="공개 기술 근거가 있습니다.",
                    confidence=EvidenceConfidence.HIGH,
                    evidence_refs=(evidence_ref,),
                ),
            ),
            job_appeal=job_appeal,
            limitations=("공개 근거 범위만 분석했습니다.",),
        ),
        contexts,
    )
    interviews = assignment.assign_interview(
        InterviewQuestionBatchDraft(
            questions=(
                InterviewQuestionDraft(
                    repository_full_name=repository.repository_full_name,
                    question="기술 선택 근거를 설명해 주세요.",
                    intent="공개 근거 설명을 확인합니다.",
                    answer_guide=("관찰 범위 안에서 설명합니다.",),
                    confidence=EvidenceConfidence.HIGH,
                    evidence_refs=(evidence_ref,),
                    criterion_context_refs=(context_ref,),
                ),
            )
        ),
        contexts,
    )
    statements = assignment.assign_statements(
        PortfolioStatementBatchDraft(
            statements=(
                PortfolioStatementDraft(
                    statement_type=PortfolioStatementType.PORTFOLIO,
                    content="공개 설정에서 기술 구성을 설명했습니다.",
                    confidence=EvidenceConfidence.HIGH,
                    evidence_refs=(evidence_ref,),
                    criterion_context_refs=(context_ref,),
                ),
            )
        ),
        contexts,
    )

    assert synthesis.overall_summary.criterion_keys == ("TECH_STACK_EVIDENCE",)
    assert interviews.questions[0].criterion_keys == ("TECH_STACK_EVIDENCE",)
    assert statements.statements[0].criterion_keys == ("TECH_STACK_EVIDENCE",)
