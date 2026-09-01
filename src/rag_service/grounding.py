from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Protocol


class EvidenceChecker(Protocol):
    """Judge whether retrieved contexts actually support the question."""

    def decide(self, question: str, contexts: list[dict[str, Any]]) -> str: ...


@dataclass(frozen=True)
class GroundingPolicy:
    """Deterministic first-pass filter before semantic evidence review.

    A vector score alone cannot prove that a chunk answers a question. This
    policy only rejects clearly unusable candidates. Candidates that pass must
    still be reviewed by an ``EvidenceChecker`` before generation.
    """

    min_contexts: int = 1
    min_score: float | None = None
    allowed_score_types: tuple[str, ...] = ("similarity", "relevance")

    def __post_init__(self) -> None:
        if self.min_contexts < 1:
            raise ValueError("min_contexts must be at least 1")

    def decide(self, contexts: Iterable[dict[str, Any]]) -> str:
        usable = [context for context in contexts if str(context.get("content", "")).strip()]
        if len(usable) < self.min_contexts:
            return "insufficient"
        if self.min_score is None:
            return "requires_review"

        for context in usable:
            score_type = str(context.get("score_type", "unknown"))
            score = context.get("retrieval_score")
            if score_type in self.allowed_score_types and isinstance(score, (int, float)) and score >= self.min_score:
                return "requires_review"
        return "insufficient"
