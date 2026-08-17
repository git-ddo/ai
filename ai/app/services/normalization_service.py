import re
from collections.abc import Iterable, Mapping
from types import MappingProxyType

from app.domain import (
    AnalysisDepth,
    InternalEvidence,
    InternalEvidenceType,
    InternalRepositoryInput,
    NormalizedRepositoryContext,
)

_TECHNOLOGY_LOOKUP_SEPARATOR = re.compile(r"[\s_-]+")
_WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:/")

DEFAULT_TECHNOLOGY_ALIASES: Mapping[str, str] = MappingProxyType(
    {
        "springboot": "Spring Boot",
        "springdatajpa": "Spring Data JPA",
        "postgres": "PostgreSQL",
        "postgresql": "PostgreSQL",
        "mysql": "MySQL",
        "githubaction": "GitHub Actions",
        "githubactions": "GitHub Actions",
        "dockercompose": "Docker Compose",
    }
)


class NormalizationError(ValueError):
    """Raised when validated input violates canonical P0 normalization rules."""


class NormalizationService:
    """Convert validated repository input into deterministic prompt context."""

    def __init__(
        self,
        technology_aliases: Mapping[str, str] | None = None,
    ) -> None:
        aliases = DEFAULT_TECHNOLOGY_ALIASES if technology_aliases is None else technology_aliases
        self._technology_aliases = self._prepare_technology_aliases(aliases)

    def normalize(
        self,
        repository: InternalRepositoryInput,
    ) -> NormalizedRepositoryContext:
        self._validate_p0_boundary(repository)

        normalized_evidence = tuple(
            sorted(
                (self._normalize_evidence(item) for item in repository.evidence),
                key=lambda item: item.evidence_id,
            )
        )
        normalized_claims = tuple(sorted(repository.user_claims, key=lambda item: item.claim_id))
        repository_technologies = self._normalize_technology_names(
            technology for item in normalized_evidence for technology in item.technology_names
        )

        try:
            return NormalizedRepositoryContext(
                repository_id=repository.repository_id,
                repository_full_name=repository.repository_full_name,
                description=repository.description,
                analysis_depth=repository.analysis_depth,
                evidence=normalized_evidence,
                user_claims=normalized_claims,
                technology_names=repository_technologies,
            )
        except ValueError as exc:
            raise NormalizationError(
                "Repository input could not be converted to normalized context."
            ) from exc

    def _normalize_evidence(self, evidence: InternalEvidence) -> InternalEvidence:
        normalized_paths = tuple(
            sorted({self._normalize_repository_path(path) for path in evidence.source_paths})
        )
        normalized_technologies = self._normalize_technology_names(evidence.technology_names)

        try:
            return InternalEvidence(
                evidence_id=evidence.evidence_id,
                repository_full_name=evidence.repository_full_name,
                evidence_type=evidence.evidence_type,
                key=evidence.key,
                summary=evidence.summary,
                source_paths=normalized_paths,
                technology_names=normalized_technologies,
            )
        except ValueError as exc:
            raise NormalizationError("Evidence normalization failed.") from exc

    @staticmethod
    def _validate_p0_boundary(repository: InternalRepositoryInput) -> None:
        if repository.analysis_depth is not AnalysisDepth.P0:
            raise NormalizationError("Only P0 repository input can be normalized.")

        allowed_evidence_types = {
            InternalEvidenceType.GITHUB_STATIC,
            InternalEvidenceType.BACKEND_DERIVED,
        }
        if any(
            evidence.evidence_type not in allowed_evidence_types for evidence in repository.evidence
        ):
            raise NormalizationError("Repository input contains non-P0 evidence.")

    @staticmethod
    def _normalize_repository_path(path: str) -> str:
        if "\x00" in path:
            raise NormalizationError("Repository path must not contain a NUL byte.")

        slash_path = path.replace("\\", "/")
        if slash_path.startswith("/") or _WINDOWS_ABSOLUTE_PATH.match(slash_path):
            raise NormalizationError("Repository path must be relative.")

        parts: list[str] = []
        for part in slash_path.split("/"):
            if part in {"", "."}:
                continue
            if part == "..":
                raise NormalizationError("Repository path must not contain '..'.")
            parts.append(part)

        if not parts:
            raise NormalizationError("Repository path must not be empty.")
        return "/".join(parts)

    def _normalize_technology_names(
        self,
        names: Iterable[str],
    ) -> tuple[str, ...]:
        normalized: list[str] = []
        for value in names:
            name = value.strip()
            if not name:
                raise NormalizationError("Technology name must not be empty.")
            lookup_key = self._technology_lookup_key(name)
            normalized.append(self._technology_aliases.get(lookup_key, name))

        ordered = sorted(normalized, key=lambda item: (item.casefold(), item))
        result: list[str] = []
        seen: set[str] = set()
        for name in ordered:
            identity = name.casefold()
            if identity in seen:
                continue
            seen.add(identity)
            result.append(name)
        return tuple(result)

    @classmethod
    def _prepare_technology_aliases(
        cls,
        aliases: Mapping[str, str],
    ) -> Mapping[str, str]:
        prepared: dict[str, str] = {}
        for raw_alias, raw_canonical_name in aliases.items():
            if not isinstance(raw_alias, str) or not isinstance(raw_canonical_name, str):
                raise NormalizationError("Technology aliases must contain string pairs.")

            alias = raw_alias.strip()
            canonical_name = raw_canonical_name.strip()
            if not alias or not canonical_name:
                raise NormalizationError("Technology aliases must not be empty.")

            lookup_key = cls._technology_lookup_key(alias)
            existing = prepared.get(lookup_key)
            if existing is not None and existing != canonical_name:
                raise NormalizationError("Technology aliases contain conflicting canonical names.")
            prepared[lookup_key] = canonical_name

        return MappingProxyType(prepared)

    @staticmethod
    def _technology_lookup_key(value: str) -> str:
        return _TECHNOLOGY_LOOKUP_SEPARATOR.sub("", value.casefold())
