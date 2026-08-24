from pathlib import Path
from typing import Final

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from app.criteria.models import (
    CriteriaLayer,
    CriteriaSet,
    CriteriaTargetJob,
)
from app.domain import AnalysisDepth


class CriteriaLoadError(Exception):
    """Base error raised while selecting or loading criteria."""


class UnsupportedCriteriaError(CriteriaLoadError):
    """Raised when the requested job and depth are not supported."""


class CriteriaFileNotFoundError(CriteriaLoadError):
    """Raised when a mapped criteria file does not exist."""


class CriteriaParseError(CriteriaLoadError):
    """Raised when criteria YAML cannot be parsed."""


class CriteriaValidationError(CriteriaLoadError):
    """Raised when parsed or cumulative criteria violate the internal schema."""


_CRITERIA_FILES: Final[dict[tuple[CriteriaTargetJob, AnalysisDepth], tuple[str, ...]]] = {
    (CriteriaTargetJob.BACKEND, AnalysisDepth.P0): ("backend.yaml",),
    (CriteriaTargetJob.BACKEND, AnalysisDepth.P1): (
        "backend.yaml",
        "backend_p1.yaml",
    ),
    (CriteriaTargetJob.BACKEND, AnalysisDepth.P2): (
        "backend.yaml",
        "backend_p1.yaml",
        "backend_p2.yaml",
    ),
}


class CriteriaLoader:
    """Load cumulative criteria through a fixed job/depth file mapping."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or Path(__file__).resolve().parent

    def load(self, target_job: str, analysis_depth: str) -> CriteriaSet:
        """Return deterministic cumulative criteria through the requested depth."""

        try:
            resolved_job = CriteriaTargetJob(target_job)
            resolved_depth = AnalysisDepth(analysis_depth)
        except ValueError as exc:
            raise UnsupportedCriteriaError(
                f"unsupported criteria combination: {target_job} × {analysis_depth}"
            ) from exc

        criteria_filenames = _CRITERIA_FILES.get((resolved_job, resolved_depth))
        if criteria_filenames is None:
            raise UnsupportedCriteriaError(
                f"unsupported criteria combination: {target_job} × {analysis_depth}"
            )

        layers = tuple(self._load_layer(filename) for filename in criteria_filenames)
        criteria = tuple(criterion for layer in layers for criterion in layer.criteria)
        guardrail_codes = tuple(
            dict.fromkeys(guardrail for layer in layers for guardrail in layer.guardrail_codes)
        )

        try:
            return CriteriaSet(
                version="1.0",
                target_job=CriteriaTargetJob.BACKEND,
                analysis_depth=resolved_depth,
                guardrail_codes=guardrail_codes,
                criteria=criteria,
            )
        except ValidationError as exc:
            raise CriteriaValidationError("cumulative criteria schema validation failed") from exc

    def _load_layer(self, criteria_filename: str) -> CriteriaLayer:
        criteria_path = self._base_dir / criteria_filename
        try:
            raw_content = criteria_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise CriteriaFileNotFoundError(
                f"criteria file not found: {criteria_filename}"
            ) from exc
        except OSError as exc:
            raise CriteriaLoadError(f"failed to read criteria file: {criteria_filename}") from exc

        try:
            parsed_content = yaml.safe_load(raw_content)
        except yaml.YAMLError as exc:
            raise CriteriaParseError(f"invalid criteria YAML: {criteria_filename}") from exc

        try:
            return CriteriaLayer.model_validate(parsed_content)
        except ValidationError as exc:
            raise CriteriaValidationError(
                f"criteria layer schema validation failed: {criteria_filename}"
            ) from exc
