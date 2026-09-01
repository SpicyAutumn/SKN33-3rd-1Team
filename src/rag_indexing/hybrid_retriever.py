from __future__ import annotations

from copy import deepcopy
from collections import Counter
from typing import Any, Protocol


class Retriever(Protocol):
    def search(self, question: str, *, top_k: int = 5) -> list[dict[str, Any]]: ...


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
    """Fuse ranked result lists without directly comparing incompatible scores.

    Pinecone cosine similarity and SQLite BM25 relevance have different
    scales.  RRF uses each system's rank instead, so the default baseline has
    no arbitrary score-normalisation rule.
    """

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
        # This is a fused relevance score, not a raw cosine or BM25 value.
        result["score_type"] = "relevance"
        fused.append(result)
    return fused


class HybridRetriever:
    """Combine Pinecone dense retrieval and local BM25 through RRF."""

    def __init__(
        self,
        dense_retriever: Retriever,
        bm25_retriever: Retriever,
        *,
        candidate_k: int = 10,
        rrf_k: int = 60,
        dense_weight: float = 1.5,
        bm25_weight: float = 1.0,
        max_chunks_per_document: int | None = None,
    ) -> None:
        if candidate_k < 1:
            raise ValueError("candidate_k must be at least 1")
        self.dense_retriever = dense_retriever
        self.bm25_retriever = bm25_retriever
        self.candidate_k = candidate_k
        self.rrf_k = rrf_k
        self.dense_weight = dense_weight
        self.bm25_weight = bm25_weight
        self.max_chunks_per_document = max_chunks_per_document

    def search(self, question: str, *, top_k: int = 5) -> list[dict[str, Any]]:
        candidate_k = max(top_k, self.candidate_k)
        dense_results = self.dense_retriever.search(question, top_k=candidate_k)
        return self.search_from_dense_results(question, dense_results, top_k=top_k)

    def search_from_dense_results(
        self, question: str, dense_results: list[dict[str, Any]], *, top_k: int = 5
    ) -> list[dict[str, Any]]:
        """Fuse a precomputed dense result list without embedding the question again."""
        candidate_k = max(top_k, self.candidate_k)
        bm25_results = self.bm25_retriever.search(question, top_k=candidate_k)
        return reciprocal_rank_fusion(
            dense_results,
            bm25_results,
            top_k=top_k,
            rrf_k=self.rrf_k,
            dense_weight=self.dense_weight,
            bm25_weight=self.bm25_weight,
            max_chunks_per_document=self.max_chunks_per_document,
        )
