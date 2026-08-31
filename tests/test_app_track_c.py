"""Track C 화면 로직 단위 테스트.

Streamlit 실행 없이 순수 함수만 확인한다. 외부 API는 호출하지 않는다.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for path in (PROJECT_ROOT / "app", PROJECT_ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import rag_client  # noqa: E402
import regions  # noqa: E402
from components.citations import group_by_document  # noqa: E402
from tabs.explore import _build_payload  # noqa: E402


def context(
    *,
    chunk_id: str,
    document_id: str,
    title: str,
    score: float | None = 0.5,
    rank: int = 1,
    section: str = "body",
    content: str = "본문",
    metadata: dict | None = None,
) -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "title": title,
        "content": content,
        "source_url": f"https://encykorea.aks.ac.kr/Article/{document_id}",
        "section": section,
        "retrieval_rank": rank,
        "retrieval_score": score,
        "score_type": "similarity",
        "metadata": metadata or {},
    }


class CitationGroupingTest(unittest.TestCase):
    def test_same_document_chunks_merge_and_keep_rank_order(self):
        groups = group_by_document(
            [
                context(chunk_id="c4", document_id="d1", title="길쌈노래", rank=4, section="classification"),
                context(chunk_id="c2", document_id="d2", title="경복궁", rank=2),
                context(chunk_id="c1", document_id="d1", title="길쌈노래", rank=1, section="definition"),
            ]
        )
        self.assertEqual([g["title"] for g in groups], ["길쌈노래", "경복궁"])
        self.assertEqual([i["section"] for i in groups[0]["items"]], ["definition", "classification"])

    def test_missing_document_id_does_not_merge_different_chunks(self):
        groups = group_by_document(
            [
                {"chunk_id": "a", "title": "같은 제목", "content": "1", "retrieval_rank": 1},
                {"chunk_id": "b", "title": "같은 제목", "content": "2", "retrieval_rank": 2},
            ]
        )
        self.assertEqual(len(groups), 2)

    def test_empty_input(self):
        self.assertEqual(group_by_document([]), [])


class EvidenceSelectionTest(unittest.TestCase):
    def test_picks_distinct_documents_up_to_limit(self):
        picked = rag_client.pick_documents(
            [
                context(chunk_id="c1", document_id="d1", title="A", rank=1),
                context(chunk_id="c2", document_id="d1", title="A", rank=2),
                context(chunk_id="c3", document_id="d2", title="B", rank=3),
                context(chunk_id="c4", document_id="d3", title="C", rank=4),
                context(chunk_id="c5", document_id="d4", title="D", rank=5),
            ],
            limit=3,
        )
        self.assertEqual([p["document_id"] for p in picked], ["d1", "d2", "d3"])


class EvidenceCheckerTest(unittest.TestCase):
    def setUp(self):
        self.checker = rag_client.ScoreEvidenceChecker(min_score=0.40)

    def test_sufficient_when_any_context_meets_threshold(self):
        contexts = [context(chunk_id="c1", document_id="d1", title="A", score=0.44)]
        self.assertEqual(self.checker.decide("q", contexts), "sufficient")

    def test_insufficient_when_all_below_threshold(self):
        contexts = [context(chunk_id="c1", document_id="d1", title="A", score=0.33)]
        self.assertEqual(self.checker.decide("q", contexts), "insufficient")

    def test_missing_score_is_not_rejected(self):
        contexts = [context(chunk_id="c1", document_id="d1", title="A", score=None)]
        self.assertEqual(self.checker.decide("q", contexts), "sufficient")

    def test_no_contexts_is_insufficient(self):
        self.assertEqual(self.checker.decide("q", []), "insufficient")


class GeneratorContractTest(unittest.TestCase):
    REQUIRED = {
        "schema_version",
        "request_id",
        "interaction_id",
        "candidate_response_type",
        "draft_message",
        "audience_level",
        "used_chunk_ids",
        "clarification",
        "premise_correction",
        "related_topic_candidates",
        "generation_metadata",
    }

    @staticmethod
    def request(contexts: list[dict], audience_level: str = "general") -> dict:
        return {
            "schema_version": "0.3.0-draft",
            "request_id": "REQ-1",
            "interaction_id": "INT-1",
            "question": "질문",
            "audience_level": audience_level,
            "response_language": "ko",
            "retrieved_contexts": contexts,
            "grounding_decision": "sufficient",
            "clarification_context": None,
        }

    def test_result_fields_match_contract_exactly(self):
        contexts = [context(chunk_id="c1", document_id="d1", title="A")]
        result = rag_client.EvidencePassthroughGenerator().invoke(self.request(contexts))
        self.assertEqual(set(result), self.REQUIRED)
        self.assertEqual(result["candidate_response_type"], "answered")
        self.assertEqual(result["used_chunk_ids"], ["c1"])
        self.assertEqual(result["audience_level"], "general")

    def test_used_chunk_ids_only_reference_input_contexts(self):
        contexts = [
            context(chunk_id="c1", document_id="d1", title="A"),
            context(chunk_id="c2", document_id="d2", title="B"),
        ]
        result = rag_client.EvidencePassthroughGenerator().invoke(self.request(contexts, "easy"))
        self.assertTrue(set(result["used_chunk_ids"]).issubset({c["chunk_id"] for c in contexts}))
        self.assertEqual(result["audience_level"], "easy")

    def test_blank_content_is_not_used_as_evidence(self):
        contexts = [
            context(chunk_id="c1", document_id="d1", title="A", content="   "),
            context(chunk_id="c2", document_id="d2", title="B", content="본문"),
        ]
        result = rag_client.EvidencePassthroughGenerator().invoke(self.request(contexts))
        self.assertEqual(result["used_chunk_ids"], ["c2"])


class RegionTest(unittest.TestCase):
    def test_title_prefix(self):
        self.assertEqual(regions.from_title("강릉 오죽헌"), "강릉")
        self.assertEqual(regions.from_title("강릉향교"), "강릉")

    def test_longer_name_wins(self):
        self.assertEqual(regions.from_title("서귀포 정방폭포"), "서귀포")

    def test_no_region_in_title(self):
        self.assertIsNone(regions.from_title("훈민정음"))

    def test_content_address_fallback(self):
        self.assertEqual(regions.from_content("경상북도 경주시 진현동에 있다."), "경상북도 경주시")
        self.assertEqual(regions.from_content("전라남도에 위치한다."), "전라남도")
        self.assertIsNone(regions.from_content("조선 후기의 문신이다."))

    def test_detect_reports_basis(self):
        self.assertEqual(regions.detect("강릉 오죽헌", "본문"), ("강릉", "제목"))
        self.assertEqual(regions.detect("훈민정음", "충청남도 공주시"), ("충청남도 공주시", "본문"))
        self.assertIsNone(regions.detect("훈민정음", "본문"))


class ExplorationMapTest(unittest.TestCase):
    METADATA = {
        "field": "종교·철학/불교",
        "era": "고대/남북국/통일신라",
        "primary_type": "유적/건물",
    }

    def test_axes_are_labelled_and_peers_linked(self):
        payload = _build_payload(
            "석굴암",
            [
                context(chunk_id="c1", document_id="d1", title="경주 석굴암 석굴", rank=1, metadata=self.METADATA),
                context(chunk_id="c2", document_id="d2", title="경주 동천동 마애삼존불", rank=2, metadata=self.METADATA),
            ],
        )
        labels = [k["keyword"] for k in payload["keywords"]]
        self.assertIn("분야 : 종교·철학/불교", labels)
        self.assertIn("시대 : 고대", labels)
        self.assertIn("지역 : 경주", labels)
        self.assertEqual(payload["root"], "경주 석굴암 석굴")
        peers = [c["keyword"] for c in payload["related"]["시대 : 고대"]]
        self.assertIn("경주 동천동 마애삼존불", peers)

    def test_no_contexts_returns_none(self):
        self.assertIsNone(_build_payload("질문", []))


if __name__ == "__main__":
    unittest.main()
