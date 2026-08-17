import pytest

from app.domain import (
    AnalysisDepth,
    InternalEvidence,
    InternalEvidenceType,
    InternalRepositoryInput,
    InternalUserClaim,
)
from app.services.normalization_service import (
    NormalizationError,
    NormalizationService,
)

REPOSITORY_NAME = "Git-Ddo/Backend"


def make_evidence(
    evidence_id: str,
    *,
    source_paths: tuple[str, ...] = ("README.md",),
    technology_names: tuple[str, ...] = (),
    key: str = "TECH_STACK_EVIDENCE",
    summary: str = "SpringBoot 의존성이 설정 파일에서 관찰되었습니다.",
) -> InternalEvidence:
    return InternalEvidence(
        evidence_id=evidence_id,
        repository_full_name=REPOSITORY_NAME,
        evidence_type=InternalEvidenceType.GITHUB_STATIC,
        key=key,
        summary=summary,
        source_paths=source_paths,
        technology_names=technology_names,
    )


def make_claim(claim_id: str) -> InternalUserClaim:
    return InternalUserClaim(
        claim_id=claim_id,
        repository_full_name=REPOSITORY_NAME,
        statement=f"사용자 진술 {claim_id}",
    )


def make_repository(
    *,
    evidence: tuple[InternalEvidence, ...] | None = None,
    user_claims: tuple[InternalUserClaim, ...] = (),
) -> InternalRepositoryInput:
    return InternalRepositoryInput(
        repository_id=123,
        repository_full_name=REPOSITORY_NAME,
        description="GitDdo Backend",
        analysis_depth=AnalysisDepth.P0,
        evidence=evidence or (make_evidence("ev_001"),),
        user_claims=user_claims,
    )


def test_normalizes_valid_repository_input() -> None:
    context = NormalizationService().normalize(make_repository())

    assert context.repository_id == 123
    assert context.repository_full_name == REPOSITORY_NAME
    assert context.description == "GitDdo Backend"
    assert context.analysis_depth is AnalysisDepth.P0


def test_normalizes_repository_paths_to_posix_form() -> None:
    repository = make_repository(
        evidence=(
            make_evidence(
                "ev_001",
                source_paths=("./src\\main//java/./App.java",),
            ),
        )
    )

    context = NormalizationService().normalize(repository)

    assert context.evidence[0].source_paths == ("src/main/java/App.java",)


def test_preserves_repository_and_file_name_case() -> None:
    repository = make_repository(
        evidence=(make_evidence("ev_001", source_paths=("Src/Main/App.java",)),)
    )

    context = NormalizationService().normalize(repository)

    assert context.repository_full_name == "Git-Ddo/Backend"
    assert context.evidence[0].source_paths == ("Src/Main/App.java",)


def test_removes_duplicate_paths_after_normalization() -> None:
    repository = make_repository(
        evidence=(
            make_evidence(
                "ev_001",
                source_paths=("./src/App.java", "src//App.java", "src\\App.java"),
            ),
        )
    )

    context = NormalizationService().normalize(repository)

    assert context.evidence[0].source_paths == ("src/App.java",)


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "C:\\secret.txt",
        "../secret.txt",
        "src/../../secret.txt",
    ],
)
def test_rejects_absolute_and_parent_traversal_paths(path: str) -> None:
    repository = make_repository(evidence=(make_evidence("ev_001", source_paths=(path,)),))

    with pytest.raises(NormalizationError):
        NormalizationService().normalize(repository)


def test_rejects_path_that_becomes_empty() -> None:
    invalid_evidence = make_evidence("ev_001").model_copy(update={"source_paths": ("./",)})
    repository = make_repository(evidence=(invalid_evidence,))

    with pytest.raises(NormalizationError, match="must not be empty"):
        NormalizationService().normalize(repository)


def test_rejects_path_with_nul_byte() -> None:
    invalid_evidence = make_evidence("ev_001").model_copy(
        update={"source_paths": ("src/\x00secret.txt",)}
    )
    repository = make_repository(evidence=(invalid_evidence,))

    with pytest.raises(NormalizationError, match="NUL"):
        NormalizationService().normalize(repository)


def test_normalizes_known_technology_aliases() -> None:
    repository = make_repository(
        evidence=(
            make_evidence(
                "ev_001",
                technology_names=(
                    "SpringBoot",
                    "spring-data-jpa",
                    "postgres",
                    "mysql",
                    "github actions",
                    "docker-compose",
                ),
            ),
        )
    )

    context = NormalizationService().normalize(repository)

    assert context.technology_names == (
        "Docker Compose",
        "GitHub Actions",
        "MySQL",
        "PostgreSQL",
        "Spring Boot",
        "Spring Data JPA",
    )
    assert context.evidence[0].technology_names == context.technology_names


def test_preserves_unknown_technology_spelling() -> None:
    repository = make_repository(
        evidence=(make_evidence("ev_001", technology_names=("GraphQL Yoga",)),)
    )

    context = NormalizationService().normalize(repository)

    assert context.technology_names == ("GraphQL Yoga",)


def test_removes_duplicate_technology_names_after_normalization() -> None:
    repository = make_repository(
        evidence=(
            make_evidence(
                "ev_001",
                technology_names=("SpringBoot", "spring-boot", "spring boot"),
            ),
        )
    )

    context = NormalizationService().normalize(repository)

    assert context.technology_names == ("Spring Boot",)
    assert context.evidence[0].technology_names == ("Spring Boot",)


def test_aggregates_repository_technology_names_from_all_evidence() -> None:
    repository = make_repository(
        evidence=(
            make_evidence("ev_002", technology_names=("postgresql",)),
            make_evidence("ev_001", technology_names=("SpringBoot",)),
        )
    )

    context = NormalizationService().normalize(repository)

    assert context.technology_names == ("PostgreSQL", "Spring Boot")


def test_supports_injected_technology_aliases() -> None:
    repository = make_repository(evidence=(make_evidence("ev_001", technology_names=("py",)),))
    service = NormalizationService(technology_aliases={"py": "Python"})

    context = service.normalize(repository)

    assert context.technology_names == ("Python",)


def test_preserves_evidence_and_claim_identifiers_and_claim_statement() -> None:
    claim = make_claim("claim_001")
    repository = make_repository(
        evidence=(make_evidence("ev_001"),),
        user_claims=(claim,),
    )

    context = NormalizationService().normalize(repository)

    assert context.evidence[0].evidence_id == "ev_001"
    assert context.user_claims[0].claim_id == "claim_001"
    assert context.user_claims[0].statement == claim.statement


def test_sorts_evidence_and_claims_by_identifier() -> None:
    repository = make_repository(
        evidence=(make_evidence("ev_002"), make_evidence("ev_001")),
        user_claims=(make_claim("claim_002"), make_claim("claim_001")),
    )

    context = NormalizationService().normalize(repository)

    assert [item.evidence_id for item in context.evidence] == ["ev_001", "ev_002"]
    assert [item.claim_id for item in context.user_claims] == [
        "claim_001",
        "claim_002",
    ]


def test_does_not_mutate_input() -> None:
    repository = make_repository(
        evidence=(
            make_evidence(
                "ev_001",
                source_paths=("./src\\App.java",),
                technology_names=("spring-boot",),
            ),
        )
    )
    before = repository.model_dump()

    NormalizationService().normalize(repository)

    assert repository.model_dump() == before


def test_normalization_is_deterministic_and_idempotent() -> None:
    service = NormalizationService()
    repository = make_repository(
        evidence=(
            make_evidence(
                "ev_001",
                source_paths=("./src\\App.java",),
                technology_names=("spring-boot",),
            ),
        ),
        user_claims=(make_claim("claim_001"),),
    )

    first = service.normalize(repository)
    second = service.normalize(repository)
    normalized_input = InternalRepositoryInput(
        repository_id=first.repository_id,
        repository_full_name=first.repository_full_name,
        description=first.description,
        analysis_depth=first.analysis_depth,
        evidence=first.evidence,
        user_claims=first.user_claims,
    )

    assert first == second
    assert service.normalize(normalized_input) == first


def test_rejects_non_p0_depth_instead_of_filtering() -> None:
    repository = make_repository().model_copy(update={"analysis_depth": "P1"})

    with pytest.raises(NormalizationError, match="Only P0"):
        NormalizationService().normalize(repository)


def test_rejects_non_p0_evidence_instead_of_filtering() -> None:
    invalid_evidence = make_evidence("ev_001").model_copy(
        update={"evidence_type": "GITHUB_ACTIVITY"}
    )
    repository = make_repository(evidence=(invalid_evidence,))

    with pytest.raises(NormalizationError, match="non-P0 evidence"):
        NormalizationService().normalize(repository)


def test_keeps_distinct_evidence_ids_even_when_content_matches() -> None:
    repository = make_repository(evidence=(make_evidence("ev_002"), make_evidence("ev_001")))

    context = NormalizationService().normalize(repository)

    assert [item.evidence_id for item in context.evidence] == ["ev_001", "ev_002"]


def test_does_not_extract_or_rewrite_technology_in_free_text() -> None:
    evidence = make_evidence(
        "ev_001",
        technology_names=(),
        key="spring-boot SHOULD_NOT_CHANGE",
        summary="spring-boot와 postgres가 문장에 있지만 구조화된 기술명은 아닙니다.",
    )
    repository = make_repository(evidence=(evidence,))

    context = NormalizationService().normalize(repository)

    assert context.evidence[0].key == evidence.key
    assert context.evidence[0].summary == evidence.summary
    assert context.technology_names == ()
