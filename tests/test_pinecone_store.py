from __future__ import annotations

import unittest

from rag_indexing.pinecone_store import EMBEDDING_INPUT_VERSION, PineconeRetriever, _flat_metadata, embedding_text
from rag_indexing.pipeline import build_chunks


PAYLOAD = {
    "eid": "E0002452",
    "status": "success",
    "url": "https://encykorea.aks.ac.kr/Article/E0002452",
    "headword": "경복궁 향원정",
    "field": "예술·체육/건축",
    "era": "조선/조선 후기",
    "primaryType": "유적/건물",
    "definition": "서울특별시 종로구 경복궁에 있는 조선후기 궁궐 건물.",
    "body": "향원정은 왕과 가족의 휴식처로 이용되었다.",
    "articleAliases": [{"word": "향원정"}],
}


class PineconeStoreTests(unittest.TestCase):
    def test_embedding_input_uses_selected_fields_and_records_version(self) -> None:
        chunk = build_chunks([PAYLOAD])[0]
        text = embedding_text(chunk)
        self.assertIn("제목: 경복궁 향원정", text)
        self.assertIn("구역: 정의", text)
        self.assertIn("시대: 조선/조선 후기", text)
        self.assertIn("유형: 유적/건물", text)
        self.assertIn("이칭: 향원정", text)
        self.assertIn("본문:", text)
        self.assertEqual(_flat_metadata(chunk)["embedding_input_version"], EMBEDDING_INPUT_VERSION)
        self.assertEqual(_flat_metadata(chunk)["source"], PAYLOAD["url"])

    def test_search_returns_track_b_source_and_page_contract_from_legacy_metadata(self) -> None:
        class FakeIndex:
            def query(self, **_: object) -> dict[str, object]:
                return {
                    "matches": [
                        {
                            "id": "aks:E0002452:test:definition:0001",
                            "score": 0.91,
                            "metadata": {
                                "document_id": "aks:E0002452",
                                "title": "경복궁 향원정",
                                "content": "향원정은 궁궐 건물이다.",
                                "source_url": PAYLOAD["url"],
                                "section": "definition",
                                "era": "조선/조선 후기",
                            },
                        }
                    ]
                }

        retriever = object.__new__(PineconeRetriever)
        retriever._embed = lambda _: [[0.1, 0.2]]
        retriever._index = FakeIndex()
        retriever.namespace = ""

        result = retriever.search("향원정은 무엇이야?", top_k=3)

        self.assertEqual(result[0]["source"], PAYLOAD["url"])
        self.assertIsNone(result[0]["page"])
        self.assertNotIn("source_url", result[0])
        self.assertEqual(result[0]["retrieval_rank"], 1)
        self.assertEqual(result[0]["metadata"], {"era": "조선/조선 후기"})

    def test_search_returns_empty_list_when_pinecone_has_no_matches(self) -> None:
        class FakeIndex:
            def __init__(self) -> None:
                self.query_kwargs: dict[str, object] | None = None

            def query(self, **kwargs: object) -> dict[str, object]:
                self.query_kwargs = kwargs
                return {"matches": []}

        retriever = object.__new__(PineconeRetriever)
        retriever._embed = lambda _: [[0.1, 0.2]]
        retriever._index = FakeIndex()
        retriever.namespace = "aks-test"

        self.assertEqual(retriever.search("없는 질문", top_k=3), [])
        self.assertEqual(retriever._index.query_kwargs["namespace"], "aks-test")

    def test_search_assigns_rank_and_handles_missing_score_and_empty_fields(self) -> None:
        class FakeIndex:
            def query(self, **_: object) -> dict[str, object]:
                return {
                    "matches": [
                        {
                            "id": "first",
                            "metadata": {
                                "document_id": "aks:E0000001",
                                "title": "첫 문서",
                                "content": "첫 본문",
                                "source": "",
                                "section": "",
                                "page": None,
                            },
                        },
                        {
                            "id": "second",
                            "score": 0.5,
                            "metadata": {
                                "document_id": "aks:E0000002",
                                "title": "둘째 문서",
                                "content": "둘째 본문",
                                "source": "https://example.test/2",
                                "section": "body",
                            },
                        },
                    ]
                }

        retriever = object.__new__(PineconeRetriever)
        retriever._embed = lambda _: [[0.1, 0.2]]
        retriever._index = FakeIndex()
        retriever.namespace = ""

        results = retriever.search("질문", top_k=2)

        self.assertEqual([item["retrieval_rank"] for item in results], [1, 2])
        self.assertIsNone(results[0]["retrieval_score"])
        self.assertEqual(results[0]["score_type"], "unknown")
        self.assertIsNone(results[0]["source"])
        self.assertIsNone(results[0]["page"])
        self.assertIsNone(results[0]["section"])
        self.assertEqual(results[1]["retrieval_score"], 0.5)
        self.assertEqual(results[1]["score_type"], "similarity")
        self.assertEqual(
            set(results[0]),
            {
                "chunk_id",
                "document_id",
                "title",
                "content",
                "source",
                "page",
                "section",
                "retrieval_rank",
                "retrieval_score",
                "score_type",
                "metadata",
            },
        )

    def test_resume_skips_only_matching_chunking_identity(self) -> None:
        chunk = build_chunks([PAYLOAD])[0]

        class FakeIndex:
            def __init__(self, metadata: dict[str, object]) -> None:
                self.metadata = metadata

            def fetch(self, **_: object) -> dict[str, object]:
                return {"vectors": {chunk.chunk_id: {"metadata": self.metadata}}}

        matching_metadata = {
            "embedding_input_version": EMBEDDING_INPUT_VERSION,
            "chunking_version": chunk.metadata["chunking_version"],
            "chunking_fingerprint": chunk.metadata["chunking_fingerprint"],
        }
        retriever = object.__new__(PineconeRetriever)
        retriever.namespace = ""
        retriever._index = FakeIndex(matching_metadata)
        self.assertEqual(retriever._current_embedding_ids([chunk]), {chunk.chunk_id})

        retriever._index = FakeIndex({**matching_metadata, "chunking_fingerprint": "different"})
        self.assertEqual(retriever._current_embedding_ids([chunk]), set())

    def test_upsert_skips_current_vectors_and_uploads_only_remaining_chunks(self) -> None:
        chunks = build_chunks([PAYLOAD])
        already_indexed, pending = chunks
        matching_metadata = {
            "embedding_input_version": EMBEDDING_INPUT_VERSION,
            "chunking_version": already_indexed.metadata["chunking_version"],
            "chunking_fingerprint": already_indexed.metadata["chunking_fingerprint"],
        }

        class FakeIndex:
            def __init__(self) -> None:
                self.upserts: list[dict[str, object]] = []

            def fetch(self, **_: object) -> dict[str, object]:
                return {"vectors": {already_indexed.chunk_id: {"metadata": matching_metadata}}}

            def upsert(self, **kwargs: object) -> None:
                self.upserts.append(kwargs)

        retriever = object.__new__(PineconeRetriever)
        retriever._embed = lambda texts: [[0.1, 0.2] for _ in texts]
        retriever._index = FakeIndex()
        retriever.namespace = "aks-test"

        result = retriever.upsert(chunks, batch_size=2, resume=True)

        self.assertEqual(result, {"uploaded": 1, "skipped_current": 1, "total": 2})
        self.assertEqual(len(retriever._index.upserts), 1)
        self.assertEqual(retriever._index.upserts[0]["namespace"], "aks-test")
        self.assertEqual(retriever._index.upserts[0]["vectors"][0]["id"], pending.chunk_id)


if __name__ == "__main__":
    unittest.main()
