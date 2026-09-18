import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.domain import (
    AnalysisItemType,
    EvidenceConfidence,
    GroundedAnalysisItem,
    InterviewQuestion,
    InterviewQuestionBatch,
    PortfolioStatement,
    PortfolioStatementBatch,
    PortfolioStatementType,
    PortfolioSynthesis,
    RepositoryAnalysis,
    RepresentativeProject,
)
from app.llm import GenerationMetadata, StructuredGeneration
from app.llm.provider import GenerationCall
from app.mappers import RequestWireMapper, ResponseWireMapper
from app.schemas.request import PortfolioReportRequest
from app.services import NormalizationService, PortfolioReportService
from app.validators import AnalysisDepthValidator, EvidenceReferenceValidator

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "technology-grounded-p2-request.json"
MIXED_EVIDENCE_REFS = ("ev_003", "ev_005", "ev_006")
MIXED_CRITERION_KEYS = (
    "TECH_STACK_EVIDENCE",
    "CHANGE_AREA_OBSERVATION",
    "INPUT_VALIDATION_OBSERVATION",
)
MIXED_CONTENT = "제공된 snippet 범위에서 Spring Boot 설정, 변경 경로와 null 입력 검증이 관찰됩니다."


class SequencedFakeProvider:
    def __init__(self, outputs: Sequence[BaseModel]) -> None:
        self._outputs = list(outputs)
        self.calls: list[GenerationCall] = []

    async def generate_structured[T: BaseModel](
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
    ) -> StructuredGeneration[T]:
        self.calls.append(
            GenerationCall(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=response_model,
            )
        )
        output = self._outputs.pop(0)
        assert isinstance(output, response_model)
        return StructuredGeneration(
            value=output,
            metadata=GenerationMetadata(duration_ms=1, attempt_count=1),
        )

    async def aclose(self) -> None:
        return None


def mixed_item(item_type: AnalysisItemType) -> GroundedAnalysisItem:
    return GroundedAnalysisItem(
        item_type=item_type,
        content=MIXED_CONTENT,
        confidence=EvidenceConfidence.HIGH,
        evidence_refs=MIXED_EVIDENCE_REFS,
        criterion_keys=MIXED_CRITERION_KEYS,
        technology_names=("Spring Boot",),
        file_paths=("build.gradle", "src/App.java"),
    )


def code_observation() -> GroundedAnalysisItem:
    return GroundedAnalysisItem(
        item_type=AnalysisItemType.OBSERVATION,
        content="제공된 snippet 범위에서 null 입력 검증이 관찰됩니다.",
        confidence=EvidenceConfidence.HIGH,
        evidence_refs=("ev_006",),
        criterion_keys=("INPUT_VALIDATION_OBSERVATION",),
        file_paths=("src/App.java",),
    )


def make_outputs() -> tuple[BaseModel, ...]:
    repository_name = "git-ddo/backend"
    analysis = RepositoryAnalysis(
        repository_full_name=repository_name,
        summary=mixed_item(AnalysisItemType.INTERPRETATION),
        observations=(code_observation(),),
        limitations=("제공된 공개 근거와 snippet 범위만 분석했습니다.",),
    )
    synthesis = PortfolioSynthesis(
        overall_summary=mixed_item(AnalysisItemType.INTERPRETATION),
        representative_projects=(
            RepresentativeProject(
                repository_full_name=repository_name,
                reason="P0, P1, P2 공개 근거를 함께 설명할 수 있습니다.",
                confidence=EvidenceConfidence.HIGH,
                evidence_refs=MIXED_EVIDENCE_REFS,
            ),
        ),
        job_appeal=mixed_item(AnalysisItemType.JOB_APPEAL),
        limitations=("제공된 공개 근거와 snippet 범위만 분석했습니다.",),
    )
    questions = InterviewQuestionBatch(
        questions=(
            InterviewQuestion(
                repository_full_name=repository_name,
                question="제공된 snippet 범위의 입력 검증을 어떻게 설명하시겠습니까?",
                intent="깊이가 다른 공개 근거를 구분해 설명하는지 확인합니다.",
                answer_guide=("P0 설정, P1 변경 경로, P2 snippet을 구분합니다.",),
                confidence=EvidenceConfidence.HIGH,
                evidence_refs=MIXED_EVIDENCE_REFS,
                criterion_keys=MIXED_CRITERION_KEYS,
                technology_names=("Spring Boot",),
                file_paths=("build.gradle", "src/App.java"),
            ),
        )
    )
    statements = PortfolioStatementBatch(
        statements=(
            PortfolioStatement(
                statement_type=PortfolioStatementType.PORTFOLIO,
                content=MIXED_CONTENT,
                confidence=EvidenceConfidence.HIGH,
                evidence_refs=MIXED_EVIDENCE_REFS,
                criterion_keys=MIXED_CRITERION_KEYS,
                technology_names=("Spring Boot",),
                file_paths=("build.gradle", "src/App.java"),
            ),
        )
    )
    return analysis, synthesis, questions, statements


@pytest.mark.asyncio
async def test_technology_grounding_crosses_the_complete_fake_provider_boundary() -> None:
    request = PortfolioReportRequest.model_validate_json(FIXTURE_PATH.read_text(encoding="utf-8"))
    internal = RequestWireMapper().to_internal(request)

    EvidenceReferenceValidator().validate(internal)
    AnalysisDepthValidator().validate(internal)
    context = NormalizationService().normalize(internal.repositories[0])
    assert context.technology_names == ("Spring Boot",)
    assert next(
        evidence for evidence in context.evidence if evidence.evidence_id == "ev_003"
    ).technology_names == ("Spring Boot",)

    provider = SequencedFakeProvider(make_outputs())
    report = await PortfolioReportService(provider).generate(
        internal,
        question_count=1,
        statement_count=1,
    )
    response = ResponseWireMapper().to_wire(
        request,
        report,
        evaluator_version="fake-boundary-1.0",
    )

    assert response.schema_version == "1.1"
    assert response.used_evidence_levels == ["P0", "P1", "P2"]
    assert len(provider.calls) == 4
    for call in provider.calls:
        assert "criterionContexts" in call.user_prompt
        assert "evidenceCriterionCompatibility" not in call.user_prompt
        repository_data = call.user_prompt.split("[UNTRUSTED_REPOSITORY_DATA_BEGIN]\n", 1)[1].split(
            "\n[UNTRUSTED_REPOSITORY_DATA_END]", 1
        )[0]
        parsed_repository_data = json.loads(repository_data)
        criterion_contexts = parsed_repository_data["criterionContexts"]
        assert any("ev_003" in context["eligible_evidence_refs"] for context in criterion_contexts)
