from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path

from rag_indexing.hybrid_retriever import HybridRetriever


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "evaluate_hybrid_retrieval.py"
SPEC = importlib.util.spec_from_file_location("evaluate_hybrid_retrieval", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _context(chunk_id: str, document_id: str, rank: int) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "title": chunk_id,
        "content": "본문",
        "source_url": None,
        "section": "body",
        "retrieval_rank": rank,
        "retrieval_score": 1.0,
        "score_type": "similarity",
        "metadata": {},
    }


class _FakeRetriever:
    def __init__(self, results: list[dict[str, object]]) -> None:
        self.results = results
        self.requested_top_k: int | None = None

    def search(self, _: str, *, top_k: int = 5) -> list[dict[str, object]]:
        self.requested_top_k = top_k
        return deepcopy(self.results[:top_k])


def test_comparison_reports_dense_bm25_and_hybrid_rank_metrics() -> None:
    dense = _FakeRetriever(
        [
            _context("dense-only", "aks:other", 1),
            _context("target", "aks:target", 2),
        ]
    )
    bm25 = _FakeRetriever(
        [
            _context("target", "aks:target", 1),
            _context("bm25-only", "aks:other-bm25", 2),
        ]
    )
    hybrid = HybridRetriever(dense, bm25, candidate_k=10, dense_weight=1.5, bm25_weight=1.0)
    case = {
        "case_id": "TEST-001",
        "expected_response_type": "answered",
        "question": "대상 질문",
        "expected_document_ids": ["aks:target"],
    }

    report = MODULE.evaluate_comparison(dense, bm25, hybrid, [case], top_k=3)

    assert dense.requested_top_k == 10
    assert bm25.requested_top_k == 10
    assert report["dense"]["hit_at_1"] == 0.0
    assert report["dense"]["hit_at_k"] == 1.0
    assert report["dense"]["mrr"] == 0.5
    assert report["bm25"]["hit_at_1"] == 1.0
    assert report["hybrid"]["hit_at_1"] == 1.0
    assert report["hybrid"]["mean_total_query_seconds"] >= report["dense"]["mean_query_seconds"]
