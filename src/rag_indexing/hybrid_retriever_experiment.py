"""Experimental RRF variant used only by the retrieval tuning script.

The production ``hybrid_retriever`` remains aligned with main/PR #19.  This
module preserves the document-level chunk cap evaluated in the experiment.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any


def reciprocal_rank_fusion(
    dense_results: list[dict[str, Any]],
    bm25_results: list[dict[str, Any]],
    *,
    top_k: int,
    rrf_k: int = 60,
    dense_weight: float = 1.0,
    bm25_weight: float = 1.0,
    max_chunks_per_document: int | None = None,
) -> list[dict[str, Any]]:
    """Fuse ranked results, optionally limiting chunks from one document."""
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    if rrf_k < 0:
        raise ValueError("rrf_k must be non-negative")
    if dense_weight < 0 or bm25_weight < 0:
        raise ValueError("retriever weights must be non-negative")
    if max_chunks_per_document is not None and max_chunks_per_document < 1:
        raise ValueError("max_chunks_per_document must be at least 1")

    candidates: dict[str, dict[str, Any]] = {}
    scores: dict[str, float] = {}
    for results, weight in ((dense_results, dense_weight), (bm25_results, bm25_weight)):
        for result in results:
            chunk_id = str(result["chunk_id"])
            rank = result.get("retrieval_rank")
            if not isinstance(rank, int) or rank < 1:
                raise ValueError("every result must have a positive retrieval_rank")
            if chunk_id not in candidates:
                candidates[chunk_id] = deepcopy(result)
                scores[chunk_id] = 0.0
            scores[chunk_id] += weight / (rrf_k + rank)

    ranked_ids: list[str] = []
    document_counts: Counter[str] = Counter()
    for chunk_id in sorted(scores, key=lambda candidate_id: (-scores[candidate_id], candidate_id)):
        document_id = str(candidates[chunk_id].get("document_id", ""))
        if max_chunks_per_document is not None and document_counts[document_id] >= max_chunks_per_document:
            continue
        ranked_ids.append(chunk_id)
        document_counts[document_id] += 1
        if len(ranked_ids) == top_k:
            break

    fused: list[dict[str, Any]] = []
    for rank, chunk_id in enumerate(ranked_ids, start=1):
        result = candidates[chunk_id]
        result["retrieval_rank"] = rank
        result["retrieval_score"] = scores[chunk_id]
        result["score_type"] = "relevance"
        fused.append(result)
    return fused
