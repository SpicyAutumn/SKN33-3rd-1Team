from __future__ import annotations

from pathlib import Path

from rag_indexing.bm25_store import BM25Retriever, build_bm25_index, tokenize_korean
from rag_indexing.hybrid_retriever import HybridRetriever, reciprocal_rank_fusion


def _context(chunk_id: str, rank: int, score: float) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "document_id": f"aks:{chunk_id}",
        "title": chunk_id,
        "content": f"{chunk_id} 본문",
        "source_url": None,
        "section": "body",
        "retrieval_rank": rank,
        "retrieval_score": score,
        "score_type": "similarity",
        "metadata": {
            "aliases": [],
            "document_fingerprint": f"fingerprint-{chunk_id}",
            "chunking_fingerprint": None,
        },
    }


def test_tokenize_korean_keeps_a_postposition_free_proper_noun() -> None:
    assert "경복궁에" in tokenize_korean("경복궁에 대해 알려줘")
    assert "경복궁" in tokenize_korean("경복궁에 대해 알려줘")


def test_bm25_index_returns_contract_contexts(tmp_path: Path) -> None:
    chunks = [
        {
            "chunk_id": "palace",
            "document_id": "aks:palace",
            "title": "경복궁",
            "content": "경복궁은 조선시대 궁궐이다.",
            "source_url": "https://example.test/palace",
            "section": "definition",
            "metadata": {
                "aliases": ["경복궁"],
                "era": "조선",
                "document_fingerprint": "fingerprint-palace",
            },
        },
        {
            "chunk_id": "other",
            "document_id": "aks:other",
            "title": "다른 건물",
            "content": "다른 설명이다.",
            "source_url": None,
            "section": "body",
            "metadata": {"document_fingerprint": "fingerprint-other"},
        },
    ]
    database = tmp_path / "aks.sqlite3"
    assert build_bm25_index(chunks, database) == 2

    results = BM25Retriever(database).search("경복궁에 대해 알려줘", top_k=3)

    assert [result["chunk_id"] for result in results] == ["palace"]
    assert results[0]["score_type"] == "relevance"
    assert results[0]["metadata"]["chunking_fingerprint"] is None


def test_bm25_prioritizes_an_exact_title_over_a_document_that_only_mentions_it(tmp_path: Path) -> None:
    chunks = [
        {
            "chunk_id": "main-palace",
            "document_id": "aks:main-palace",
            "title": "경복궁",
            "content": "조선시대 궁궐이다.",
            "source_url": None,
            "section": "definition",
            "metadata": {"document_fingerprint": "fingerprint-main-palace"},
        },
        {
            "chunk_id": "palace-building",
            "document_id": "aks:palace-building",
            "title": "경복궁 사정전",
            "content": "경복궁에 있는 건물 경복궁 경복궁 경복궁.",
            "source_url": None,
            "section": "definition",
            "metadata": {"document_fingerprint": "fingerprint-palace-building"},
        },
    ]
    database = tmp_path / "aks.sqlite3"
    build_bm25_index(chunks, database)

    results = BM25Retriever(database).search("경복궁에 대해 알려줘", top_k=2)

    assert [result["chunk_id"] for result in results] == ["main-palace", "palace-building"]


def test_bm25_keeps_exact_title_results_for_known_heritage_terms(tmp_path: Path) -> None:
    names = ("경복궁", "향원정", "석굴암", "종묘")
    chunks = [
        {
            "chunk_id": f"chunk-{name}",
            "document_id": f"aks:{name}",
            "title": name,
            "content": f"{name}에 대한 공식 설명.",
            "source_url": None,
            "section": "definition",
            "metadata": {"aliases": [], "document_fingerprint": f"fingerprint-{name}"},
        }
        for name in names
    ]
    database = tmp_path / "aks.sqlite3"
    build_bm25_index(chunks, database)

    for name in names:
        assert BM25Retriever(database).search(f"{name}은 무엇이야?", top_k=3)[0]["title"] == name


def test_bm25_rejects_a_chunk_without_contract_fingerprint(tmp_path: Path) -> None:
    chunks = [
        {
            "chunk_id": "missing-fingerprint",
            "document_id": "aks:missing-fingerprint",
            "title": "경복궁",
            "content": "궁궐이다.",
            "source_url": None,
            "section": "definition",
            "metadata": {"aliases": []},
        }
    ]

    try:
        build_bm25_index(chunks, tmp_path / "aks.sqlite3")
    except ValueError as exc:
        assert "document_fingerprint" in str(exc)
    else:
        raise AssertionError("BM25 index must reject a missing document_fingerprint")


def test_rrf_promotes_a_document_found_by_both_retrievers() -> None:
    dense = [_context("semantic-only", 1, 0.9), _context("target", 2, 0.8)]
    bm25 = [_context("target", 1, 10.0), _context("keyword-only", 2, 9.0)]

    results = reciprocal_rank_fusion(dense, bm25, top_k=3, rrf_k=60)

    assert [result["chunk_id"] for result in results] == ["target", "semantic-only", "keyword-only"]
    assert results[0]["retrieval_rank"] == 1
    assert results[0]["score_type"] == "relevance"


def test_hybrid_retriever_requests_candidate_lists_before_final_top_k() -> None:
    class FakeRetriever:
        def __init__(self, results: list[dict[str, object]]) -> None:
            self.results = results
            self.requested_top_k: int | None = None

        def search(self, _: str, *, top_k: int = 5) -> list[dict[str, object]]:
            self.requested_top_k = top_k
            return self.results

    dense = FakeRetriever([_context("dense", 1, 0.9)])
    bm25 = FakeRetriever([_context("bm25", 1, 9.0)])
    hybrid = HybridRetriever(dense, bm25, candidate_k=10)

    results = hybrid.search("질문", top_k=3)

    assert dense.requested_top_k == 10
    assert bm25.requested_top_k == 10
    assert len(results) == 2


def test_hybrid_retriever_can_fuse_a_precomputed_dense_search() -> None:
    class FakeBM25:
        def search(self, _: str, *, top_k: int = 5) -> list[dict[str, object]]:
            assert top_k == 10
            return [_context("bm25", 1, 9.0)]

    hybrid = HybridRetriever(object(), FakeBM25(), candidate_k=10)
    results = hybrid.search_from_dense_results("질문", [_context("dense", 1, 0.9)], top_k=3)

    assert [result["chunk_id"] for result in results] == ["dense", "bm25"]
