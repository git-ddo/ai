import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

from app.core.exceptions import ResponseMappingError
from app.domain import (
    AnalysisItemType,
    EvidenceConfidence,
    GroundedAnalysisItem,
    InternalGenerationRecord,
    InternalGenerationStage,
    InternalPortfolioReport,
    InterviewQuestion,
    PortfolioAnalysis,
    PortfolioStatement,
    PortfolioStatementType,
    PortfolioSynthesis,
    RecommendationPriority,
    RepositoryAnalysis,
    RepresentativeProject,
)
from app.mappers import ResponseWireMapper
from app.schemas.common import (
    AnalysisDepth,
    Confidence,
    FindingCategory,
    FindingSeverity,
    LimitationCode,
)
from app.schemas.request import PortfolioReportRequest
from app.schemas.response import PortfolioReportResponse

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "contracts" / "backend_contract"

_CRITERION_BY_DEPTH = {
    AnalysisDepth.P0: "README_READINESS",
    AnalysisDepth.P1: "ACTIVITY_SCOPE",
    AnalysisDepth.P2: "SNIPPET_SCOPE",
}


def load_request(depth: AnalysisDepth = AnalysisDepth.P0) -> PortfolioReportRequest:
    path = FIXTURES_DIR / f"analysis-request.{depth.value.casefold()}.example.json"
    with path.open(encoding="utf-8") as fixture_file:
        raw: object = json.load(fixture_file)
    if not isinstance(raw, dict):
        raise TypeError("Request fixture must contain an object")
    return PortfolioReportRequest.model_validate(raw)


def make_item(
    *,
    item_type: AnalysisItemType,
    evidence_refs: tuple[str, ...],
    criterion_keys: tuple[str, ...],
    content: str = "전달된 근거 범위에서 확인한 분석 내용입니다.",
    confidence: EvidenceConfidence = EvidenceConfidence.HIGH,
    claim_refs: tuple[str, ...] = (),
    file_paths: tuple[str, ...] = (),
    priority: RecommendationPriority | None = None,
) -> GroundedAnalysisItem:
    return GroundedAnalysisItem(
        item_type=item_type,
        content=content,
        confidence=confidence,
        evidence_refs=evidence_refs,
        claim_refs=claim_refs,
        criterion_keys=criterion_keys,
        file_paths=file_paths,
        priority=priority,
    )


def make_report(
    request: PortfolioReportRequest,
    *,
    criterion_key: str | None = None,
    confidence: EvidenceConfidence = EvidenceConfidence.HIGH,
    coaching_claim_refs: tuple[str, ...] = (),
    include_all_depths: bool = True,
) -> InternalPortfolioReport:
    analyses: list[RepositoryAnalysis] = []
    questions: list[InterviewQuestion] = []
    statements: list[PortfolioStatement] = []
    repository_records: list[InternalGenerationRecord] = []
    interview_records: list[InternalGenerationRecord] = []
    all_refs: list[str] = []
    all_criteria: list[str] = []
    deepest_ref_by_repository: dict[str, str] = {}

    for repository in request.repositories:
        deepest = max(
            repository.evidence,
            key=lambda item: list(AnalysisDepth).index(item.analysis_depth),
        )
        deepest_ref_by_repository[repository.repository_full_name] = deepest.evidence_id
        resolved_criterion = criterion_key or _CRITERION_BY_DEPTH[deepest.analysis_depth]
        path_refs = (deepest.path,) if deepest.path is not None else ()
        refs_by_depth: dict[AnalysisDepth, str] = {}
        for evidence in repository.evidence:
            refs_by_depth.setdefault(evidence.analysis_depth, evidence.evidence_id)
        summary_refs = (
            tuple(refs_by_depth.values()) if include_all_depths else (deepest.evidence_id,)
        )
        summary_criteria = (
            tuple(_CRITERION_BY_DEPTH[depth] for depth in refs_by_depth)
            if include_all_depths
            else (resolved_criterion,)
        )
        all_refs.extend(summary_refs)
        all_criteria.extend(summary_criteria)

        summary = make_item(
            item_type=AnalysisItemType.INTERPRETATION,
            evidence_refs=summary_refs,
            criterion_keys=summary_criteria,
            content=f"{repository.repository_full_name} 분석 요약입니다.",
            confidence=confidence,
        )
        observation = make_item(
            item_type=AnalysisItemType.OBSERVATION,
            evidence_refs=(deepest.evidence_id,),
            criterion_keys=(resolved_criterion,),
            content="관찰 내용입니다.",
            confidence=confidence,
            file_paths=path_refs,
        )
        strength = make_item(
            item_type=AnalysisItemType.INTERPRETATION,
            evidence_refs=(deepest.evidence_id,),
            criterion_keys=(resolved_criterion,),
            content="확인된 강점입니다.",
            confidence=confidence,
            file_paths=path_refs,
        )
        recommendation = make_item(
            item_type=AnalysisItemType.RECOMMENDATION,
            evidence_refs=(deepest.evidence_id,),
            criterion_keys=(resolved_criterion,),
            content="근거에 기반한 개선 제안입니다.",
            confidence=confidence,
            file_paths=path_refs,
            priority=RecommendationPriority.MEDIUM,
        )
        analyses.append(
            RepositoryAnalysis(
                repository_full_name=repository.repository_full_name,
                summary=summary,
                observations=(observation,),
                strengths=(strength,),
                recommendations=(recommendation,),
                limitations=("전달된 근거 범위만 사용했습니다.",),
            )
        )
        questions.append(
            InterviewQuestion(
                repository_full_name=repository.repository_full_name,
                question="이 근거를 프로젝트 경험과 어떻게 연결하시겠습니까?",
                intent="공개 근거를 설명하는 방식을 확인합니다.",
                answer_guide=("근거의 경로와 관찰 범위를 먼저 설명합니다.",),
                follow_up_questions=("이 근거의 한계는 무엇인가요?",),
                confidence=confidence,
                evidence_refs=(deepest.evidence_id,),
                criterion_keys=(resolved_criterion,),
                file_paths=path_refs,
            )
        )
        statements.append(
            PortfolioStatement(
                statement_type=PortfolioStatementType.PORTFOLIO,
                content="공개 근거를 바탕으로 프로젝트 경험을 설명했습니다.",
                confidence=confidence,
                evidence_refs=(deepest.evidence_id,),
                criterion_keys=(resolved_criterion,),
                file_paths=path_refs,
            )
        )
        repository_records.append(
            InternalGenerationRecord(
                stage=InternalGenerationStage.REPOSITORY,
                repository_full_name=repository.repository_full_name,
                duration_ms=1,
                attempt_count=1,
            )
        )
        interview_records.append(
            InternalGenerationRecord(
                stage=InternalGenerationStage.INTERVIEW,
                repository_full_name=repository.repository_full_name,
                duration_ms=1,
                attempt_count=1,
            )
        )

    global_refs = tuple(dict.fromkeys(all_refs))
    global_criteria = tuple(dict.fromkeys(all_criteria))
    coaching_item = make_item(
        item_type=AnalysisItemType.INTERPRETATION,
        evidence_refs=global_refs,
        claim_refs=coaching_claim_refs,
        criterion_keys=global_criteria,
        confidence=confidence,
    )
    next_action = make_item(
        item_type=AnalysisItemType.RECOMMENDATION,
        evidence_refs=global_refs,
        claim_refs=coaching_claim_refs,
        criterion_keys=global_criteria,
        confidence=confidence,
        priority=RecommendationPriority.MEDIUM,
    )
    job_appeal = make_item(
        item_type=AnalysisItemType.JOB_APPEAL,
        evidence_refs=global_refs,
        claim_refs=coaching_claim_refs,
        criterion_keys=global_criteria,
        confidence=confidence,
    )
    synthesis = PortfolioSynthesis(
        overall_summary=coaching_item,
        representative_projects=tuple(
            RepresentativeProject(
                repository_full_name=repository.repository_full_name,
                reason="대표 프로젝트 후보입니다.",
                confidence=confidence,
                evidence_refs=(
                    (repository.evidence[0].evidence_id,)
                    if include_all_depths
                    else (deepest_ref_by_repository[repository.repository_full_name],)
                ),
            )
            for repository in request.repositories
        ),
        strengths=(coaching_item,),
        gaps=(coaching_item,),
        next_actions=(next_action,),
        job_appeal=job_appeal,
        limitations=("전달된 근거 범위만 사용했습니다.",),
    )
    analysis = PortfolioAnalysis(
        repository_analyses=tuple(analyses),
        synthesis=synthesis,
        interview_questions=tuple(questions),
        portfolio_statements=tuple(statements),
    )
    return InternalPortfolioReport(
        analysis=analysis,
        generation_records=(
            *repository_records,
            InternalGenerationRecord(
                stage=InternalGenerationStage.PORTFOLIO,
                duration_ms=1,
                attempt_count=1,
            ),
            *interview_records,
            InternalGenerationRecord(
                stage=InternalGenerationStage.STATEMENT,
                duration_ms=1,
                attempt_count=1,
            ),
        ),
    )


def add_second_repository(raw: dict[str, Any]) -> None:
    second = deepcopy(raw["repositories"][0])
    second["repositoryId"] = "456"
    second["repositoryFullName"] = "git-ddo/second"
    second["snapshotSha"] = "second-snapshot"
    evidence_id_map: dict[str, str] = {}
    for index, evidence in enumerate(second["evidence"], start=101):
        old_id = evidence["evidenceId"]
        new_id = f"ev_{index:03d}"
        evidence_id_map[old_id] = new_id
        evidence["evidenceId"] = new_id
        evidence["repositoryId"] = "456"
        evidence["repositoryFullName"] = "git-ddo/second"
        evidence["snapshotSha"] = "second-snapshot"
    for evidence in second["evidence"]:
        evidence["sourceEvidenceRefs"] = [
            evidence_id_map.get(reference, reference)
            for reference in evidence["sourceEvidenceRefs"]
        ]
    for index, claim in enumerate(second["userClaims"], start=101):
        claim["claimId"] = f"claim_{index:03d}"
        claim["relatedEvidenceRefs"] = [
            evidence_id_map.get(reference, reference) for reference in claim["relatedEvidenceRefs"]
        ]
    raw["repositories"].append(second)


def load_request_data(depth: AnalysisDepth = AnalysisDepth.P0) -> dict[str, Any]:
    path = FIXTURES_DIR / f"analysis-request.{depth.value.casefold()}.example.json"
    with path.open(encoding="utf-8") as fixture_file:
        raw: object = json.load(fixture_file)
    if not isinstance(raw, dict):
        raise TypeError("Request fixture must contain an object")
    return cast(dict[str, Any], raw)


def map_report(
    request: PortfolioReportRequest,
    report: InternalPortfolioReport | None = None,
    *,
    evaluator_version: str = "gemini-prompt-1.0",
) -> PortfolioReportResponse:
    return ResponseWireMapper().to_wire(
        request,
        report or make_report(request),
        evaluator_version=evaluator_version,
    )


@pytest.mark.parametrize("depth", list(AnalysisDepth))
def test_maps_valid_internal_report_for_each_depth(depth: AnalysisDepth) -> None:
    request = load_request(depth)

    response = map_report(request)

    assert response.schema_version == "1.1"
    assert response.analysis_id == request.analysis_id
    assert response.requested_analysis_depth is depth
    assert response.summary == "전달된 근거 범위에서 확인한 분석 내용입니다."


def test_copies_repository_identity_and_snapshot_from_request() -> None:
    request = load_request()
    repository = request.repositories[0]

    result = map_report(request).repositories[0]

    assert result.repository_id == repository.repository_id
    assert result.repository_full_name == repository.repository_full_name
    assert result.snapshot_hash_algorithm is repository.snapshot_hash_algorithm
    assert result.snapshot_sha == repository.snapshot_sha


def test_preserves_request_repository_order_and_uses_global_finding_sequence() -> None:
    raw = load_request_data()
    add_second_repository(raw)
    request = PortfolioReportRequest.model_validate(raw)

    result = map_report(request)

    assert [repository.repository_id for repository in result.repositories] == ["123", "456"]
    finding_ids = [
        finding.finding_id for repository in result.repositories for finding in repository.findings
    ]
    assert finding_ids == [
        "find_001",
        "find_002",
        "find_003",
        "find_004",
        "find_005",
        "find_006",
    ]
    assert [finding.detail for finding in result.repositories[0].findings] == [
        "관찰 내용입니다.",
        "확인된 강점입니다.",
        "근거에 기반한 개선 제안입니다.",
    ]


@pytest.mark.parametrize(
    ("depth", "criterion_key", "expected"),
    [
        (AnalysisDepth.P0, "README_READINESS", FindingCategory.DOCUMENTATION),
        (AnalysisDepth.P0, "TECH_STACK_EVIDENCE", FindingCategory.STACK),
        (AnalysisDepth.P0, "TEST_PRESENCE", FindingCategory.STRUCTURE),
        (AnalysisDepth.P0, "DOCKER_CONFIGURATION", FindingCategory.STACK),
        (AnalysisDepth.P0, "GITHUB_ACTIONS_CONFIGURATION", FindingCategory.STACK),
        (AnalysisDepth.P1, "ACTIVITY_SCOPE", FindingCategory.ACTIVITY),
        (AnalysisDepth.P1, "CHANGE_AREA_OBSERVATION", FindingCategory.ACTIVITY),
        (AnalysisDepth.P1, "CLAIM_ACTIVITY_LINK", FindingCategory.CONTRIBUTION),
        (AnalysisDepth.P2, "SNIPPET_SCOPE", FindingCategory.CODE_QUALITY),
        (AnalysisDepth.P2, "INPUT_VALIDATION_OBSERVATION", FindingCategory.CODE_QUALITY),
        (AnalysisDepth.P2, "ERROR_HANDLING_OBSERVATION", FindingCategory.CODE_QUALITY),
        (AnalysisDepth.P2, "RESPONSIBILITY_OBSERVATION", FindingCategory.CODE_QUALITY),
        (AnalysisDepth.P2, "TEST_CASE_OBSERVATION", FindingCategory.CODE_QUALITY),
    ],
)
def test_maps_criterion_to_finding_category(
    depth: AnalysisDepth,
    criterion_key: str,
    expected: FindingCategory,
) -> None:
    request = load_request(depth)

    result = map_report(request, make_report(request, criterion_key=criterion_key))

    assert {finding.category for finding in result.repositories[0].findings} == {expected}


def test_accepts_multiple_criteria_resolving_to_same_category() -> None:
    request = load_request(AnalysisDepth.P1)
    report = make_report(request)
    analysis = report.analysis.repository_analyses[0]
    observation = analysis.observations[0].model_copy(
        update={"criterion_keys": ("ACTIVITY_SCOPE", "CHANGE_AREA_OBSERVATION")}
    )
    report = replace_repository_analysis(
        report,
        analysis.model_copy(update={"observations": (observation,)}),
    )

    result = map_report(request, report)

    assert result.repositories[0].findings[0].category is FindingCategory.ACTIVITY


@pytest.mark.parametrize(
    "criteria",
    [("UNKNOWN",), ("README_READINESS", "TECH_STACK_EVIDENCE")],
)
def test_rejects_unknown_or_ambiguous_finding_criteria(criteria: tuple[str, ...]) -> None:
    request = load_request()
    report = make_report(request)
    analysis = report.analysis.repository_analyses[0]
    observation = analysis.observations[0].model_copy(update={"criterion_keys": criteria})
    report = replace_repository_analysis(
        report,
        analysis.model_copy(update={"observations": (observation,)}),
    )

    with pytest.raises(ResponseMappingError, match="criterion|category"):
        map_report(request, report)


def test_maps_finding_severity_title_and_detail() -> None:
    result = map_report(load_request()).repositories[0].findings

    assert [item.severity for item in result] == [
        FindingSeverity.INFO,
        FindingSeverity.POSITIVE,
        FindingSeverity.GAP,
    ]
    assert [item.title for item in result] == ["문서 관찰", "문서 강점", "문서 개선 제안"]


def test_high_priority_recommendation_maps_to_risk() -> None:
    request = load_request()
    report = make_report(request)
    analysis = report.analysis.repository_analyses[0]
    recommendation = analysis.recommendations[0].model_copy(
        update={"priority": RecommendationPriority.HIGH}
    )
    report = replace_repository_analysis(
        report,
        analysis.model_copy(update={"recommendations": (recommendation,)}),
    )

    result = map_report(request, report)

    assert result.repositories[0].findings[-1].severity is FindingSeverity.RISK


@pytest.mark.parametrize(
    ("internal", "wire"),
    [
        (EvidenceConfidence.HIGH, Confidence.HIGH),
        (EvidenceConfidence.MEDIUM, Confidence.MEDIUM),
        (EvidenceConfidence.LOW, Confidence.LOW),
        (EvidenceConfidence.NOT_VERIFIABLE, Confidence.LOW),
    ],
)
def test_maps_confidence(internal: EvidenceConfidence, wire: Confidence) -> None:
    request = load_request()

    result = map_report(request, make_report(request, confidence=internal))

    assert result.repositories[0].findings[0].confidence is wire
    assert result.coaching.portfolio_statements[0].confidence is wire
    assert result.coaching.interview_questions[0].confidence is wire


def test_maps_statement_and_question_fields() -> None:
    result = map_report(load_request()).coaching

    statement = result.portfolio_statements[0]
    assert statement.text == "공개 근거를 바탕으로 프로젝트 경험을 설명했습니다."
    assert statement.evidence_refs == ["ev_001"]
    question = result.interview_questions[0]
    assert question.answer_guide == ["근거의 경로와 관찰 범위를 먼저 설명합니다."]
    assert question.follow_up_questions == ["이 근거의 한계는 무엇인가요?"]


@pytest.mark.parametrize(
    ("depth", "expected_levels", "expected_limitations"),
    [
        (AnalysisDepth.P0, [AnalysisDepth.P0], [LimitationCode.P0_ONLY]),
        (
            AnalysisDepth.P1,
            [AnalysisDepth.P0, AnalysisDepth.P1],
            [LimitationCode.MISSING_CODE_EVIDENCE],
        ),
        (
            AnalysisDepth.P2,
            [AnalysisDepth.P0, AnalysisDepth.P1, AnalysisDepth.P2],
            [],
        ),
    ],
)
def test_calculates_used_levels_and_limitations(
    depth: AnalysisDepth,
    expected_levels: list[AnalysisDepth],
    expected_limitations: list[LimitationCode],
) -> None:
    result = map_report(load_request(depth))

    assert result.used_evidence_levels == expected_levels
    assert [limitation.code for limitation in result.limitations] == expected_limitations


def test_used_levels_follow_transitive_source_evidence() -> None:
    request = load_request(AnalysisDepth.P2)
    report = make_report(request, include_all_depths=False)
    assert all(
        reference != "ev_002" for reference in ResponseWireMapper._iter_report_evidence_refs(report)
    )

    result = map_report(request, report)

    assert result.used_evidence_levels == [AnalysisDepth.P1, AnalysisDepth.P2]


def test_builds_all_missing_depth_limitations_when_p2_request_uses_only_p0() -> None:
    request = load_request(AnalysisDepth.P0).model_copy(
        update={"requested_analysis_depth": AnalysisDepth.P2}
    )

    result = map_report(request)

    assert result.used_evidence_levels == [AnalysisDepth.P0]
    assert [limitation.code for limitation in result.limitations] == [
        LimitationCode.P0_ONLY,
        LimitationCode.MISSING_ACTIVITY_EVIDENCE,
        LimitationCode.MISSING_CODE_EVIDENCE,
    ]


def test_rejects_evidence_deeper_than_requested_depth() -> None:
    request = load_request(AnalysisDepth.P1).model_copy(
        update={"requested_analysis_depth": AnalysisDepth.P0}
    )

    with pytest.raises(ResponseMappingError, match="requested depth"):
        map_report(request)


def test_rejects_evidence_outside_repository_completed_levels() -> None:
    request = load_request(AnalysisDepth.P1)
    repository = request.repositories[0].model_copy(
        update={"completed_evidence_levels": [AnalysisDepth.P0]}
    )
    request = request.model_copy(update={"repositories": [repository]})

    with pytest.raises(ResponseMappingError, match="completed levels"):
        map_report(request)


def test_rejects_unknown_source_evidence_reference() -> None:
    request = load_request(AnalysisDepth.P2)
    repository = request.repositories[0]
    evidence = list(repository.evidence)
    evidence[-1] = evidence[-1].model_copy(update={"source_evidence_refs": ["ev_999"]})
    repository = repository.model_copy(update={"evidence": evidence})
    request = request.model_copy(update={"repositories": [repository]})

    with pytest.raises(ResponseMappingError, match="unknown source evidence"):
        map_report(request, make_report(request, include_all_depths=False))


def test_rejects_source_evidence_cycle() -> None:
    request = load_request(AnalysisDepth.P2)
    repository = request.repositories[0]
    evidence = list(repository.evidence)
    cycle_index = next(index for index, item in enumerate(evidence) if item.evidence_id == "ev_002")
    evidence[cycle_index] = evidence[cycle_index].model_copy(
        update={"source_evidence_refs": ["ev_005"]}
    )
    repository = repository.model_copy(update={"evidence": evidence})
    request = request.model_copy(update={"repositories": [repository]})

    with pytest.raises(ResponseMappingError, match="cycle"):
        map_report(request, make_report(request, include_all_depths=False))


@pytest.mark.parametrize("reference_kind", ["evidence", "claim"])
def test_rejects_unknown_references(reference_kind: str) -> None:
    request = load_request()
    report = make_report(request)
    analysis = report.analysis.repository_analyses[0]
    updates = (
        {"evidence_refs": ("ev_999",)}
        if reference_kind == "evidence"
        else {"claim_refs": ("claim_999",)}
    )
    observation = analysis.observations[0].model_copy(update=updates)
    report = replace_repository_analysis(
        report,
        analysis.model_copy(update={"observations": (observation,)}),
    )

    with pytest.raises(ResponseMappingError, match="unknown"):
        map_report(request, report)


def test_rejects_cross_repository_finding_reference() -> None:
    raw = load_request_data()
    add_second_repository(raw)
    request = PortfolioReportRequest.model_validate(raw)
    report = make_report(request)
    first = report.analysis.repository_analyses[0]
    second_evidence = request.repositories[1].evidence[0].evidence_id
    observation = first.observations[0].model_copy(update={"evidence_refs": (second_evidence,)})
    report = replace_repository_analysis(
        report,
        first.model_copy(update={"observations": (observation,)}),
    )

    with pytest.raises(ResponseMappingError, match="cross-repository"):
        map_report(request, report)


def test_rejects_cross_repository_interview_reference() -> None:
    raw = load_request_data()
    add_second_repository(raw)
    request = PortfolioReportRequest.model_validate(raw)
    report = make_report(request)
    question = report.analysis.interview_questions[0].model_copy(
        update={"evidence_refs": (request.repositories[1].evidence[0].evidence_id,)}
    )
    analysis = report.analysis.model_copy(
        update={
            "interview_questions": (
                question,
                *report.analysis.interview_questions[1:],
            )
        }
    )
    report = report.model_copy(update={"analysis": analysis})

    with pytest.raises(ResponseMappingError, match="cross-repository"):
        map_report(request, report)


def test_rejects_repository_set_mismatch() -> None:
    raw = load_request_data()
    add_second_repository(raw)
    request = PortfolioReportRequest.model_validate(raw)
    report = make_report(request)
    analysis = report.analysis.model_copy(
        update={"repository_analyses": report.analysis.repository_analyses[:1]}
    )
    report = report.model_copy(update={"analysis": analysis})

    with pytest.raises(ResponseMappingError, match="same repositories"):
        map_report(request, report)


def test_rejects_duplicate_internal_repository_name() -> None:
    request = load_request()
    report = make_report(request)
    analysis = report.analysis.model_copy(
        update={"repository_analyses": report.analysis.repository_analyses * 2}
    )
    report = report.model_copy(update={"analysis": analysis})

    with pytest.raises(ResponseMappingError, match="duplicate repository"):
        map_report(request, report)


def test_rejects_duplicate_request_repository_name() -> None:
    request = load_request()
    request = request.model_copy(update={"repositories": request.repositories * 2})

    with pytest.raises(ResponseMappingError, match="duplicate repository"):
        map_report(request, make_report(load_request()))


@pytest.mark.parametrize(
    ("depth", "criterion_key", "expected_message"),
    [
        (AnalysisDepth.P1, "ACTIVITY_SCOPE", "ACTIVITY finding requires P1"),
        (AnalysisDepth.P2, "SNIPPET_SCOPE", "CODE_QUALITY finding requires P2"),
    ],
)
def test_rejects_finding_without_category_required_depth(
    depth: AnalysisDepth,
    criterion_key: str,
    expected_message: str,
) -> None:
    request = load_request(depth)
    report = make_report(request, criterion_key=criterion_key)
    analysis = report.analysis.repository_analyses[0]
    shallow_evidence = request.repositories[0].evidence[0].evidence_id
    observation = analysis.observations[0].model_copy(update={"evidence_refs": (shallow_evidence,)})
    report = replace_repository_analysis(
        report,
        analysis.model_copy(update={"observations": (observation,)}),
    )

    with pytest.raises(ResponseMappingError, match=expected_message):
        map_report(request, report)


def test_rejects_blank_evaluator_version() -> None:
    with pytest.raises(ResponseMappingError, match="Evaluator version"):
        map_report(load_request(), evaluator_version="   ")


def test_rejects_claim_refs_that_coaching_wire_items_cannot_represent() -> None:
    request = load_request()
    report = make_report(request, coaching_claim_refs=("claim_001",))

    with pytest.raises(ResponseMappingError, match="claim refs"):
        map_report(request, report)


def test_does_not_mutate_inputs_and_serializes_backend_camel_case() -> None:
    request = load_request()
    report = make_report(request)
    request_before = request.model_dump()
    report_before = report.model_dump()

    result = map_report(request, report)
    dumped = result.model_dump(mode="json", by_alias=True)

    assert request.model_dump() == request_before
    assert report.model_dump() == report_before
    assert dumped["schemaVersion"] == "1.1"
    assert "analysisId" in dumped
    assert "repositoryFullName" in dumped["repositories"][0]
    assert "followUpQuestions" in dumped["coaching"]["interviewQuestions"][0]


def test_excludes_internal_only_fields_from_wire_output() -> None:
    dumped = map_report(load_request()).model_dump(mode="json", by_alias=True)
    serialized = json.dumps(dumped)

    for excluded in (
        "criterionKeys",
        "technologyNames",
        "generationRecords",
        "representativeProjects",
        "statementType",
    ):
        assert excluded not in serialized


def test_wraps_wire_pydantic_validation_error() -> None:
    request = load_request()
    report = make_report(request)
    analysis = report.analysis.repository_analyses[0]
    observation = analysis.observations[0].model_copy(update={"file_paths": ("../secret",)})
    report = replace_repository_analysis(
        report,
        analysis.model_copy(update={"observations": (observation,)}),
    )

    with pytest.raises(ResponseMappingError, match="valid Backend response"):
        map_report(request, report)


def replace_repository_analysis(
    report: InternalPortfolioReport,
    replacement: RepositoryAnalysis,
) -> InternalPortfolioReport:
    analyses = tuple(
        replacement
        if analysis.repository_full_name == replacement.repository_full_name
        else analysis
        for analysis in report.analysis.repository_analyses
    )
    portfolio = report.analysis.model_copy(update={"repository_analyses": analyses})
    return report.model_copy(update={"analysis": portfolio})
