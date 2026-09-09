from collections.abc import Iterable, Sequence

from pydantic import ValidationError

from app.core.exceptions import ResponseMappingError
from app.domain import (
    EvidenceConfidence,
    GroundedAnalysisItem,
    InternalPortfolioReport,
    RecommendationPriority,
    RepositoryAnalysis,
)
from app.domain import (
    InterviewQuestion as InternalInterviewQuestion,
)
from app.domain import (
    PortfolioStatement as InternalPortfolioStatement,
)
from app.schemas.common import (
    AnalysisDepth as WireAnalysisDepth,
)
from app.schemas.common import (
    Confidence as WireConfidence,
)
from app.schemas.common import (
    FindingCategory,
    FindingSeverity,
    LimitationCode,
)
from app.schemas.repository import Evidence, RepositoryInput
from app.schemas.request import PortfolioReportRequest
from app.schemas.response import (
    Coaching,
    CoachingItem,
    Finding,
    InterviewQuestion,
    JobAppeal,
    Limitation,
    PortfolioReportResponse,
    PortfolioStatement,
    RepositoryReport,
)

_DEPTH_RANK = {
    WireAnalysisDepth.P0: 0,
    WireAnalysisDepth.P1: 1,
    WireAnalysisDepth.P2: 2,
}

_CRITERION_CATEGORIES = {
    "README_READINESS": FindingCategory.DOCUMENTATION,
    "TECH_STACK_EVIDENCE": FindingCategory.STACK,
    "TEST_PRESENCE": FindingCategory.STRUCTURE,
    "DOCKER_CONFIGURATION": FindingCategory.STACK,
    "GITHUB_ACTIONS_CONFIGURATION": FindingCategory.STACK,
    "ACTIVITY_SCOPE": FindingCategory.ACTIVITY,
    "CHANGE_AREA_OBSERVATION": FindingCategory.ACTIVITY,
    "CLAIM_ACTIVITY_LINK": FindingCategory.CONTRIBUTION,
    "SNIPPET_SCOPE": FindingCategory.CODE_QUALITY,
    "INPUT_VALIDATION_OBSERVATION": FindingCategory.CODE_QUALITY,
    "ERROR_HANDLING_OBSERVATION": FindingCategory.CODE_QUALITY,
    "RESPONSIBILITY_OBSERVATION": FindingCategory.CODE_QUALITY,
    "TEST_CASE_OBSERVATION": FindingCategory.CODE_QUALITY,
}

_CATEGORY_LABELS = {
    FindingCategory.STRUCTURE: "구조",
    FindingCategory.DOCUMENTATION: "문서",
    FindingCategory.STACK: "기술 스택",
    FindingCategory.ACTIVITY: "활동",
    FindingCategory.CONTRIBUTION: "기여 진술",
    FindingCategory.CODE_QUALITY: "코드 근거",
}

_CONFIDENCE_MAP = {
    EvidenceConfidence.HIGH: WireConfidence.HIGH,
    EvidenceConfidence.MEDIUM: WireConfidence.MEDIUM,
    EvidenceConfidence.LOW: WireConfidence.LOW,
    EvidenceConfidence.NOT_VERIFIABLE: WireConfidence.LOW,
}

_P0_ONLY_MESSAGE = "이번 분석은 P0 근거만 사용해 구조·문서·기술 설정 범위만 해석했습니다."
_MISSING_ACTIVITY_MESSAGE = (
    "최종 리포트에서 P1 활동 근거를 사용하지 않아 활동과 기여를 확인하지 않았습니다."
)
_MISSING_CODE_MESSAGE = (
    "최종 리포트에서 P2 코드 근거를 사용하지 않아 코드 품질을 판단하지 않았습니다."
)


class ResponseWireMapper:
    """Convert a validated internal report into the Backend response v1.1 contract."""

    def to_wire(
        self,
        request: PortfolioReportRequest,
        report: InternalPortfolioReport,
        *,
        evaluator_version: str,
    ) -> PortfolioReportResponse:
        if not evaluator_version.strip():
            raise ResponseMappingError("Evaluator version must not be blank.")

        try:
            return self._to_wire(request, report, evaluator_version=evaluator_version)
        except ValidationError as exc:
            raise ResponseMappingError(
                "Internal report could not form a valid Backend response."
            ) from exc

    def _to_wire(
        self,
        request: PortfolioReportRequest,
        report: InternalPortfolioReport,
        *,
        evaluator_version: str,
    ) -> PortfolioReportResponse:

        request_repositories = self._index_request_repositories(request.repositories)
        analyses = self._index_repository_analyses(report.analysis.repository_analyses)
        if set(request_repositories) != set(analyses):
            raise ResponseMappingError(
                "Wire request and internal report must contain the same repositories."
            )

        evidence_by_id, evidence_owners = self._index_evidence(request.repositories)
        claim_owners = self._index_claims(request.repositories)
        self._validate_report_references(
            report,
            evidence_owners=evidence_owners,
            claim_owners=claim_owners,
        )
        used_levels = self._resolve_used_evidence_levels(
            report,
            request,
            request_repositories,
            evidence_by_id,
            evidence_owners,
        )

        finding_sequence = 1
        repository_reports: list[RepositoryReport] = []
        for repository in request.repositories:
            analysis = analyses[repository.repository_full_name]
            findings, finding_sequence = self._map_findings(
                analysis,
                repository.repository_full_name,
                evidence_by_id,
                evidence_owners,
                claim_owners,
                finding_sequence,
            )
            repository_reports.append(
                RepositoryReport(
                    repository_id=repository.repository_id,
                    repository_full_name=repository.repository_full_name,
                    snapshot_hash_algorithm=repository.snapshot_hash_algorithm,
                    snapshot_sha=repository.snapshot_sha,
                    findings=findings,
                )
            )

        return PortfolioReportResponse(
            schema_version="1.1",
            analysis_id=request.analysis_id,
            evaluator_version=evaluator_version,
            requested_analysis_depth=request.requested_analysis_depth,
            used_evidence_levels=used_levels,
            summary=report.analysis.synthesis.overall_summary.content,
            repositories=repository_reports,
            coaching=self._map_coaching(
                report,
                evidence_owners=evidence_owners,
                claim_owners=claim_owners,
            ),
            limitations=self._build_limitations(
                request.requested_analysis_depth,
                used_levels,
            ),
        )

    @staticmethod
    def _index_request_repositories(
        repositories: Sequence[RepositoryInput],
    ) -> dict[str, RepositoryInput]:
        indexed: dict[str, RepositoryInput] = {}
        for repository in repositories:
            if repository.repository_full_name in indexed:
                raise ResponseMappingError("Wire request contains a duplicate repository name.")
            indexed[repository.repository_full_name] = repository
        return indexed

    @staticmethod
    def _index_repository_analyses(
        analyses: Sequence[RepositoryAnalysis],
    ) -> dict[str, RepositoryAnalysis]:
        indexed: dict[str, RepositoryAnalysis] = {}
        for analysis in analyses:
            if analysis.repository_full_name in indexed:
                raise ResponseMappingError("Internal report contains a duplicate repository name.")
            indexed[analysis.repository_full_name] = analysis
        return indexed

    @staticmethod
    def _index_evidence(
        repositories: Sequence[RepositoryInput],
    ) -> tuple[dict[str, Evidence], dict[str, str]]:
        evidence_by_id: dict[str, Evidence] = {}
        owners: dict[str, str] = {}
        for repository in repositories:
            for evidence in repository.evidence:
                if evidence.evidence_id in evidence_by_id:
                    raise ResponseMappingError("Wire request contains a duplicate evidence ID.")
                if evidence.repository_full_name != repository.repository_full_name:
                    raise ResponseMappingError("Wire evidence does not belong to its repository.")
                evidence_by_id[evidence.evidence_id] = evidence
                owners[evidence.evidence_id] = repository.repository_full_name
        return evidence_by_id, owners

    @staticmethod
    def _index_claims(repositories: Sequence[RepositoryInput]) -> dict[str, str]:
        owners: dict[str, str] = {}
        for repository in repositories:
            for claim in repository.user_claims:
                if claim.claim_id in owners:
                    raise ResponseMappingError("Wire request contains a duplicate claim ID.")
                owners[claim.claim_id] = repository.repository_full_name
        return owners

    def _validate_report_references(
        self,
        report: InternalPortfolioReport,
        *,
        evidence_owners: dict[str, str],
        claim_owners: dict[str, str],
    ) -> None:
        for analysis in report.analysis.repository_analyses:
            for item in self._repository_items(analysis):
                self._validate_references(
                    item.evidence_refs,
                    item.claim_refs,
                    evidence_owners,
                    claim_owners,
                    expected_repository=analysis.repository_full_name,
                )

        synthesis = report.analysis.synthesis
        for item in (
            synthesis.overall_summary,
            *synthesis.strengths,
            *synthesis.gaps,
            *synthesis.next_actions,
            synthesis.job_appeal,
        ):
            self._validate_references(
                item.evidence_refs,
                item.claim_refs,
                evidence_owners,
                claim_owners,
            )
        for project in synthesis.representative_projects:
            self._validate_references(
                project.evidence_refs,
                project.claim_refs,
                evidence_owners,
                claim_owners,
                expected_repository=project.repository_full_name,
            )
        for question in report.analysis.interview_questions:
            self._validate_references(
                question.evidence_refs,
                question.claim_refs,
                evidence_owners,
                claim_owners,
                expected_repository=question.repository_full_name,
            )
        for statement in report.analysis.portfolio_statements:
            self._validate_references(
                statement.evidence_refs,
                statement.claim_refs,
                evidence_owners,
                claim_owners,
            )

    @staticmethod
    def _validate_references(
        evidence_refs: Sequence[str],
        claim_refs: Sequence[str],
        evidence_owners: dict[str, str],
        claim_owners: dict[str, str],
        *,
        expected_repository: str | None = None,
    ) -> None:
        for evidence_ref in evidence_refs:
            owner = evidence_owners.get(evidence_ref)
            if owner is None:
                raise ResponseMappingError("Internal report references unknown evidence.")
            if expected_repository is not None and owner != expected_repository:
                raise ResponseMappingError("Internal report contains a cross-repository reference.")
        for claim_ref in claim_refs:
            owner = claim_owners.get(claim_ref)
            if owner is None:
                raise ResponseMappingError("Internal report references an unknown user claim.")
            if expected_repository is not None and owner != expected_repository:
                raise ResponseMappingError("Internal report contains a cross-repository reference.")

    def _resolve_used_evidence_levels(
        self,
        report: InternalPortfolioReport,
        request: PortfolioReportRequest,
        request_repositories: dict[str, RepositoryInput],
        evidence_by_id: dict[str, Evidence],
        evidence_owners: dict[str, str],
    ) -> list[WireAnalysisDepth]:
        direct_references = tuple(self._iter_report_evidence_refs(report))
        visited: set[str] = set()
        active: set[str] = set()

        def visit(reference: str) -> None:
            if reference in visited:
                return
            if reference in active:
                raise ResponseMappingError("Wire evidence source references contain a cycle.")
            evidence = evidence_by_id.get(reference)
            if evidence is None:
                raise ResponseMappingError("Internal report references unknown evidence.")

            owner = evidence_owners[reference]
            repository = request_repositories[owner]
            if evidence.analysis_depth not in repository.completed_evidence_levels:
                raise ResponseMappingError(
                    "Referenced evidence exceeds its repository completed levels."
                )
            if _DEPTH_RANK[evidence.analysis_depth] > _DEPTH_RANK[request.requested_analysis_depth]:
                raise ResponseMappingError("Referenced evidence exceeds the requested depth.")

            active.add(reference)
            for source_reference in evidence.source_evidence_refs:
                source_owner = evidence_owners.get(source_reference)
                if source_owner is None:
                    raise ResponseMappingError(
                        "Wire evidence references an unknown source evidence."
                    )
                if source_owner != owner:
                    raise ResponseMappingError(
                        "Wire evidence contains a cross-repository source reference."
                    )
                visit(source_reference)
            active.remove(reference)
            visited.add(reference)

        for reference in direct_references:
            visit(reference)

        if not visited:
            raise ResponseMappingError("Internal report does not use any evidence.")

        used = {evidence_by_id[reference].analysis_depth for reference in visited}
        return sorted(used, key=_DEPTH_RANK.__getitem__)

    @staticmethod
    def _repository_items(analysis: RepositoryAnalysis) -> tuple[GroundedAnalysisItem, ...]:
        return (
            analysis.summary,
            *analysis.observations,
            *analysis.strengths,
            *analysis.recommendations,
        )

    @staticmethod
    def _iter_report_evidence_refs(report: InternalPortfolioReport) -> Iterable[str]:
        for analysis in report.analysis.repository_analyses:
            for item in ResponseWireMapper._repository_items(analysis):
                yield from item.evidence_refs

        synthesis = report.analysis.synthesis
        for item in (
            synthesis.overall_summary,
            *synthesis.strengths,
            *synthesis.gaps,
            *synthesis.next_actions,
            synthesis.job_appeal,
        ):
            yield from item.evidence_refs
        for project in synthesis.representative_projects:
            yield from project.evidence_refs
        for question in report.analysis.interview_questions:
            yield from question.evidence_refs
        for statement in report.analysis.portfolio_statements:
            yield from statement.evidence_refs

    def _map_findings(
        self,
        analysis: RepositoryAnalysis,
        repository_name: str,
        evidence_by_id: dict[str, Evidence],
        evidence_owners: dict[str, str],
        claim_owners: dict[str, str],
        starting_sequence: int,
    ) -> tuple[list[Finding], int]:
        sequence = starting_sequence
        findings: list[Finding] = []
        groups = (
            (analysis.observations, "관찰"),
            (analysis.strengths, "강점"),
            (analysis.recommendations, "개선 제안"),
        )
        for items, title_suffix in groups:
            for item in items:
                self._validate_references(
                    item.evidence_refs,
                    item.claim_refs,
                    evidence_owners,
                    claim_owners,
                    expected_repository=repository_name,
                )
                category = self._map_category(item)
                self._validate_category_evidence(category, item.evidence_refs, evidence_by_id)
                findings.append(
                    Finding(
                        finding_id=f"find_{sequence:03d}",
                        category=category,
                        severity=self._map_severity(title_suffix, item),
                        confidence=self._map_confidence(item.confidence),
                        title=f"{_CATEGORY_LABELS[category]} {title_suffix}",
                        detail=item.content,
                        evidence_refs=list(item.evidence_refs),
                        claim_refs=list(item.claim_refs),
                        file_paths=list(item.file_paths),
                    )
                )
                sequence += 1
        return findings, sequence

    @staticmethod
    def _map_category(item: GroundedAnalysisItem) -> FindingCategory:
        categories: set[FindingCategory] = set()
        for criterion_key in item.criterion_keys:
            category = _CRITERION_CATEGORIES.get(criterion_key)
            if category is None:
                raise ResponseMappingError("Internal finding uses an unknown criterion key.")
            categories.add(category)
        if len(categories) != 1:
            raise ResponseMappingError(
                "Internal finding criteria do not resolve to one wire category."
            )
        return next(iter(categories))

    @staticmethod
    def _map_severity(
        title_suffix: str,
        item: GroundedAnalysisItem,
    ) -> FindingSeverity:
        if title_suffix == "관찰":
            return FindingSeverity.INFO
        if title_suffix == "강점":
            return FindingSeverity.POSITIVE
        if item.priority is RecommendationPriority.HIGH:
            return FindingSeverity.RISK
        if item.priority in {RecommendationPriority.MEDIUM, RecommendationPriority.LOW}:
            return FindingSeverity.GAP
        raise ResponseMappingError("Internal recommendation does not have a valid priority.")

    @staticmethod
    def _validate_category_evidence(
        category: FindingCategory,
        evidence_refs: Sequence[str],
        evidence_by_id: dict[str, Evidence],
    ) -> None:
        referenced_depths = {
            evidence_by_id[reference].analysis_depth
            for reference in evidence_refs
            if reference in evidence_by_id
        }
        if category is FindingCategory.ACTIVITY and WireAnalysisDepth.P1 not in referenced_depths:
            raise ResponseMappingError("ACTIVITY finding requires P1 evidence.")
        if (
            category is FindingCategory.CODE_QUALITY
            and WireAnalysisDepth.P2 not in referenced_depths
        ):
            raise ResponseMappingError("CODE_QUALITY finding requires P2 evidence.")

    @staticmethod
    def _map_confidence(confidence: EvidenceConfidence) -> WireConfidence:
        return _CONFIDENCE_MAP[confidence]

    def _map_coaching(
        self,
        report: InternalPortfolioReport,
        *,
        evidence_owners: dict[str, str],
        claim_owners: dict[str, str],
    ) -> Coaching:
        synthesis = report.analysis.synthesis
        return Coaching(
            strengths=[self._map_coaching_item(item, "strengths") for item in synthesis.strengths],
            gaps=[self._map_coaching_item(item, "gaps") for item in synthesis.gaps],
            next_actions=[
                self._map_coaching_item(item, "nextActions") for item in synthesis.next_actions
            ],
            job_appeal=self._map_job_appeal(synthesis.job_appeal),
            portfolio_statements=[
                self._map_statement(statement) for statement in report.analysis.portfolio_statements
            ],
            interview_questions=[
                self._map_question(question, evidence_owners, claim_owners)
                for question in report.analysis.interview_questions
            ],
        )

    def _map_coaching_item(
        self,
        item: GroundedAnalysisItem,
        field_name: str,
    ) -> CoachingItem:
        if item.claim_refs:
            raise ResponseMappingError(
                f"Internal {field_name} item has claim refs unsupported by the wire contract."
            )
        if not item.evidence_refs:
            raise ResponseMappingError(f"Internal {field_name} item requires evidence.")
        return CoachingItem(
            text=item.content,
            confidence=self._map_confidence(item.confidence),
            evidence_refs=list(item.evidence_refs),
        )

    def _map_job_appeal(self, item: GroundedAnalysisItem) -> JobAppeal:
        if item.claim_refs:
            raise ResponseMappingError(
                "Internal job appeal has claim refs unsupported by the wire contract."
            )
        if not item.evidence_refs:
            raise ResponseMappingError("Internal job appeal requires evidence.")
        return JobAppeal(
            text=item.content,
            confidence=self._map_confidence(item.confidence),
            evidence_refs=list(item.evidence_refs),
        )

    def _map_statement(self, statement: InternalPortfolioStatement) -> PortfolioStatement:
        return PortfolioStatement(
            text=statement.content,
            confidence=self._map_confidence(statement.confidence),
            evidence_refs=list(statement.evidence_refs),
            claim_refs=list(statement.claim_refs),
        )

    def _map_question(
        self,
        question: InternalInterviewQuestion,
        evidence_owners: dict[str, str],
        claim_owners: dict[str, str],
    ) -> InterviewQuestion:
        if question.repository_full_name not in set(evidence_owners.values()) | set(
            claim_owners.values()
        ):
            raise ResponseMappingError("Interview question references an unknown repository.")
        self._validate_references(
            question.evidence_refs,
            question.claim_refs,
            evidence_owners,
            claim_owners,
            expected_repository=question.repository_full_name,
        )
        return InterviewQuestion(
            question=question.question,
            intent=question.intent,
            answer_guide=list(question.answer_guide),
            follow_up_questions=list(question.follow_up_questions),
            confidence=self._map_confidence(question.confidence),
            evidence_refs=list(question.evidence_refs),
            claim_refs=list(question.claim_refs),
        )

    @staticmethod
    def _build_limitations(
        requested_depth: WireAnalysisDepth,
        used_levels: Sequence[WireAnalysisDepth],
    ) -> list[Limitation]:
        used = set(used_levels)
        limitations: list[Limitation] = []
        if used == {WireAnalysisDepth.P0}:
            limitations.append(Limitation(code=LimitationCode.P0_ONLY, message=_P0_ONLY_MESSAGE))
        if requested_depth is not WireAnalysisDepth.P0 and WireAnalysisDepth.P1 not in used:
            limitations.append(
                Limitation(
                    code=LimitationCode.MISSING_ACTIVITY_EVIDENCE,
                    message=_MISSING_ACTIVITY_MESSAGE,
                )
            )
        if requested_depth is not WireAnalysisDepth.P0 and WireAnalysisDepth.P2 not in used:
            limitations.append(
                Limitation(
                    code=LimitationCode.MISSING_CODE_EVIDENCE,
                    message=_MISSING_CODE_MESSAGE,
                )
            )
        return limitations


__all__ = ["ResponseWireMapper"]
