from pathlib import Path
from typing import Final

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from app.criteria.models import CriteriaAnalysisDepth, CriteriaSet, CriteriaTargetJob


class CriteriaLoadError(Exception):
    """Base error raised while selecting or loading criteria."""


class UnsupportedCriteriaError(CriteriaLoadError):
    """Raised when the requested job and depth are not supported."""


class CriteriaFileNotFoundError(CriteriaLoadError):
    """Raised when the mapped criteria file does not exist."""


class CriteriaParseError(CriteriaLoadError):
    """Raised when criteria YAML cannot be parsed."""


class CriteriaValidationError(CriteriaLoadError):
    """Raised when parsed criteria do not match the internal schema."""


_CRITERIA_FILES: Final[dict[tuple[str, str], str]] = {
    (CriteriaTargetJob.BACKEND, CriteriaAnalysisDepth.P0): "backend.yaml",
}


class CriteriaLoader:
    """Load criteria through a fixed job/depth-to-file mapping."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or Path(__file__).resolve().parent

    def load(self, target_job: str, analysis_depth: str) -> CriteriaSet:
        """Return validated criteria for a supported job and analysis depth."""

        criteria_filename = _CRITERIA_FILES.get((target_job, analysis_depth))
        if criteria_filename is None:
            raise UnsupportedCriteriaError(
                f"unsupported criteria combination: {target_job} × {analysis_depth}"
            )

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
            return CriteriaSet.model_validate(parsed_content)
        except ValidationError as exc:
            raise CriteriaValidationError(
                f"criteria schema validation failed: {criteria_filename}"
            ) from exc
