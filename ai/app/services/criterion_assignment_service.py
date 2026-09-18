from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.core.exceptions import ReportPolicyError
from app.domain import (
    GroundedAnalysisDraft,
    GroundedAnalysisItem,
    InterviewQuestion,
    InterviewQuestionBatch,
    InterviewQuestionBatchDraft,
    InterviewQuestionDraft,
    PortfolioStatement,
    PortfolioStatementBatch,
    PortfolioStatementBatchDraft,
    PortfolioStatementDraft,
    PortfolioSynthesis,
    PortfolioSynthesisDraft,
    RepositoryAnalysis,
    RepositoryAnalysisDraft,
)
from app.services.criterion_context_service import CriterionEvidenceContext
from app.validators import PolicyViolation, PolicyViolationCode


class _ContextGroundedDraft(Protocol):
    criterion_context_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    claim_refs: tuple[str, ...]


class CriterionAssignmentService:
    """Validate Criterion Context references and inject their owned Criterion keys."""

    def assign_repository(
        self,
        draft: RepositoryAnalysisDraft,
        contexts: Sequence[CriterionEvidenceContext],
    ) -> RepositoryAnalysis:
        context_items = self._validate_contexts(contexts)
        return RepositoryAnalysis(
            repository_full_name=draft.repository_full_name,
            summary=self._analysis_item(draft.summary, context_items, "summary"),
            observations=tuple(
                self._analysis_item(item, context_items, f"observations[{index}]")
                for index, item in enumerate(draft.observations)
            ),
            strengths=tuple(
                self._analysis_item(item, context_items, f"strengths[{index}]")
                for index, item in enumerate(draft.strengths)
            ),
            recommendations=tuple(
                self._analysis_item(item, context_items, f"recommendations[{index}]")
                for index, item in enumerate(draft.recommendations)
            ),
            limitations=draft.limitations,
        )

    def assign_portfolio(
        self,
        draft: PortfolioSynthesisDraft,
        contexts: Sequence[CriterionEvidenceContext],
    ) -> PortfolioSynthesis:
        context_items = self._validate_contexts(contexts)
        return PortfolioSynthesis(
            overall_summary=self._analysis_item(
                draft.overall_summary,
                context_items,
                "overall_summary",
            ),
            representative_projects=draft.representative_projects,
            strengths=tuple(
                self._analysis_item(item, context_items, f"strengths[{index}]")
                for index, item in enumerate(draft.strengths)
            ),
            gaps=tuple(
                self._analysis_item(item, context_items, f"gaps[{index}]")
                for index, item in enumerate(draft.gaps)
            ),
            next_actions=tuple(
                self._analysis_item(item, context_items, f"next_actions[{index}]")
                for index, item in enumerate(draft.next_actions)
            ),
            job_appeal=self._analysis_item(
                draft.job_appeal,
                context_items,
                "job_appeal",
            ),
            limitations=draft.limitations,
        )

    def assign_interview(
        self,
        draft: InterviewQuestionBatchDraft,
        contexts: Sequence[CriterionEvidenceContext],
    ) -> InterviewQuestionBatch:
        context_items = self._validate_contexts(contexts)
        return InterviewQuestionBatch(
            questions=tuple(
                self._interview_question(item, context_items, f"questions[{index}]")
                for index, item in enumerate(draft.questions)
            )
        )

    def assign_statements(
        self,
        draft: PortfolioStatementBatchDraft,
        contexts: Sequence[CriterionEvidenceContext],
    ) -> PortfolioStatementBatch:
        context_items = self._validate_contexts(contexts)
        return PortfolioStatementBatch(
            statements=tuple(
                self._statement(item, context_items, f"statements[{index}]")
                for index, item in enumerate(draft.statements)
            )
        )

    def _analysis_item(
        self,
        draft: GroundedAnalysisDraft,
        contexts: tuple[CriterionEvidenceContext, ...],
        field_path: str,
    ) -> GroundedAnalysisItem:
        criterion_keys = self._criterion_keys(draft, contexts, field_path)
        return GroundedAnalysisItem(
            **draft.model_dump(exclude={"criterion_context_refs", "criterion_keys"}),
            criterion_keys=criterion_keys,
        )

    def _interview_question(
        self,
        draft: InterviewQuestionDraft,
        contexts: tuple[CriterionEvidenceContext, ...],
        field_path: str,
    ) -> InterviewQuestion:
        criterion_keys = self._criterion_keys(draft, contexts, field_path)
        return InterviewQuestion(
            **draft.model_dump(exclude={"criterion_context_refs", "criterion_keys"}),
            criterion_keys=criterion_keys,
        )

    def _statement(
        self,
        draft: PortfolioStatementDraft,
        contexts: tuple[CriterionEvidenceContext, ...],
        field_path: str,
    ) -> PortfolioStatement:
        criterion_keys = self._criterion_keys(draft, contexts, field_path)
        return PortfolioStatement(
            **draft.model_dump(exclude={"criterion_context_refs", "criterion_keys"}),
            criterion_keys=criterion_keys,
        )

    def _criterion_keys(
        self,
        draft: _ContextGroundedDraft,
        contexts: tuple[CriterionEvidenceContext, ...],
        field_path: str,
    ) -> tuple[str, ...]:
        context_by_id = {context.context_id: context for context in contexts}
        context_refs = self._context_refs(draft, contexts)
        unknown_refs = tuple(ref for ref in context_refs if ref not in context_by_id)
        if unknown_refs:
            self._raise_violation(
                PolicyViolationCode.UNKNOWN_CRITERION_CONTEXT,
                f"Unknown Criterion Context references: {', '.join(unknown_refs)}.",
                f"{field_path}.criterion_context_refs",
            )

        selected = tuple(context_by_id[ref] for ref in context_refs)
        known_evidence_refs = {
            ref for context in contexts for ref in context.eligible_evidence_refs
        }
        allowed_evidence_refs = {
            ref for context in selected for ref in context.eligible_evidence_refs
        }
        disallowed_evidence_refs = tuple(
            ref
            for ref in draft.evidence_refs
            if ref in known_evidence_refs and ref not in allowed_evidence_refs
        )
        if disallowed_evidence_refs:
            self._raise_violation(
                PolicyViolationCode.CRITERION_CONTEXT_EVIDENCE_MISMATCH,
                "Evidence references fall outside the selected Criterion Contexts: "
                + ", ".join(disallowed_evidence_refs)
                + ".",
                f"{field_path}.evidence_refs",
            )

        known_claim_refs = {ref for context in contexts for ref in context.eligible_claim_refs}
        allowed_claim_refs = {ref for context in selected for ref in context.eligible_claim_refs}
        disallowed_claim_refs = tuple(
            ref
            for ref in draft.claim_refs
            if ref in known_claim_refs and ref not in allowed_claim_refs
        )
        if disallowed_claim_refs:
            self._raise_violation(
                PolicyViolationCode.CRITERION_CONTEXT_CLAIM_MISMATCH,
                "Claim references fall outside the selected Criterion Contexts: "
                + ", ".join(disallowed_claim_refs)
                + ".",
                f"{field_path}.claim_refs",
            )

        has_unknown_refs = any(
            ref not in known_evidence_refs for ref in draft.evidence_refs
        ) or any(ref not in known_claim_refs for ref in draft.claim_refs)
        unused_contexts = (
            ()
            if has_unknown_refs
            else tuple(
                context.context_id
                for context in selected
                if not set(context.eligible_evidence_refs).intersection(draft.evidence_refs)
                and not set(context.eligible_claim_refs).intersection(draft.claim_refs)
            )
        )
        if unused_contexts:
            self._raise_violation(
                PolicyViolationCode.UNUSED_CRITERION_CONTEXT,
                "Criterion Contexts do not ground a cited Evidence or Claim reference: "
                + ", ".join(unused_contexts)
                + ".",
                f"{field_path}.criterion_context_refs",
            )

        return tuple(context.criterion_key for context in selected)

    @staticmethod
    def _context_refs(
        draft: _ContextGroundedDraft,
        contexts: tuple[CriterionEvidenceContext, ...],
    ) -> tuple[str, ...]:
        if draft.criterion_context_refs:
            return draft.criterion_context_refs

        legacy_keys = getattr(draft, "criterion_keys", ())
        context_by_key = {context.criterion_key: context.context_id for context in contexts}
        return tuple(context_by_key.get(key, f"unknown:{key}") for key in legacy_keys)

    @staticmethod
    def _validate_contexts(
        contexts: Sequence[CriterionEvidenceContext],
    ) -> tuple[CriterionEvidenceContext, ...]:
        context_items = tuple(contexts)
        context_ids = [context.context_id for context in context_items]
        criterion_keys = [context.criterion_key for context in context_items]
        if not context_items:
            raise ValueError("Criterion assignment requires at least one context.")
        if len(context_ids) != len(set(context_ids)):
            raise ValueError("Criterion Context IDs must be unique.")
        if len(criterion_keys) != len(set(criterion_keys)):
            raise ValueError("Criterion Context keys must be unique.")
        return context_items

    @staticmethod
    def _raise_violation(
        code: PolicyViolationCode,
        message: str,
        field_path: str,
    ) -> None:
        raise ReportPolicyError((PolicyViolation(code, message, field_path),))


__all__ = ["CriterionAssignmentService"]
