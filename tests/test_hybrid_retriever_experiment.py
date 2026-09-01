from __future__ import annotations

from rag_indexing.hybrid_retriever_experiment import reciprocal_rank_fusion


def _result(chunk_id: str, document_id: str, rank: int) -> dict[str, object]:
    return {"chunk_id": chunk_id, "document_id": document_id, "retrieval_rank": rank}


def test_rrf_experiment_limits_chunks_per_document_while_filling_top_k() -> None:
    dense = [
        _result("same-1", "aks:same", 1),
        _result("same-2", "aks:same", 2),
        _result("same-3", "aks:same", 3),
        _result("other-1", "aks:other-1", 4),
        _result("other-2", "aks:other-2", 5),
    ]

    results = reciprocal_rank_fusion(dense, [], top_k=3, max_chunks_per_document=1)

    assert [result["chunk_id"] for result in results] == ["same-1", "other-1", "other-2"]


def test_rrf_experiment_rejects_non_positive_document_limit() -> None:
    try:
        reciprocal_rank_fusion([], [], top_k=3, max_chunks_per_document=0)
    except ValueError as exc:
        assert "max_chunks_per_document" in str(exc)
    else:
        raise AssertionError("a non-positive document limit must be rejected")
