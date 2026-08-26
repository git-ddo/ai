import pytest

from app.domain import AnalysisDepth
from scripts.smoke_internal_report import build_smoke_input


@pytest.mark.parametrize(
    ("depth", "expected_levels", "expected_evidence_count"),
    [
        (AnalysisDepth.P0, (AnalysisDepth.P0,), 5),
        (AnalysisDepth.P1, (AnalysisDepth.P0, AnalysisDepth.P1), 6),
        (
            AnalysisDepth.P2,
            (AnalysisDepth.P0, AnalysisDepth.P1, AnalysisDepth.P2),
            8,
        ),
    ],
)
def test_build_smoke_input_limits_repository_to_requested_depth(
    depth: AnalysisDepth,
    expected_levels: tuple[AnalysisDepth, ...],
    expected_evidence_count: int,
) -> None:
    portfolio = build_smoke_input(repository_count=1, analysis_depth=depth)

    assert portfolio.requested_analysis_depth is depth
    assert len(portfolio.repositories) == 1
    assert portfolio.repositories[0].analysis_depth is depth
    assert portfolio.repositories[0].completed_evidence_levels == expected_levels
    assert len(portfolio.repositories[0].evidence) == expected_evidence_count
    assert all(
        evidence.analysis_depth in expected_levels
        for evidence in portfolio.repositories[0].evidence
    )


def test_build_smoke_input_supports_two_repositories() -> None:
    portfolio = build_smoke_input(repository_count=2, analysis_depth=AnalysisDepth.P2)

    assert len(portfolio.repositories) == 2


@pytest.mark.parametrize("repository_count", [0, 3])
def test_build_smoke_input_rejects_unsupported_repository_count(
    repository_count: int,
) -> None:
    with pytest.raises(ValueError, match="one or two repositories"):
        build_smoke_input(repository_count=repository_count)
