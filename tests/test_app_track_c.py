"""Track C 화면 로직 단위 테스트.

Streamlit 실행 없이 순수 함수만 확인한다. 외부 API는 호출하지 않는다.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for path in (PROJECT_ROOT / "app", PROJECT_ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import rag_client  # noqa: E402
import regions  # noqa: E402
import retrieval  # noqa: E402
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


class ThresholdTest(unittest.TestCase):
    """기준선 판정은 한 함수만 쓴다. 화면과 근거 선택이 같은 결과를 내야 한다."""

    def test_score_above_or_equal_passes(self):
        self.assertTrue(rag_client.meets_threshold(context(chunk_id="c", document_id="d", title="A", score=0.41)))
        self.assertTrue(rag_client.meets_threshold(context(chunk_id="c", document_id="d", title="A", score=0.40)))

    def test_score_below_fails(self):
        self.assertFalse(rag_client.meets_threshold(context(chunk_id="c", document_id="d", title="A", score=0.38)))

    def test_zero_score_is_a_real_score_and_fails(self):
        self.assertFalse(rag_client.meets_threshold(context(chunk_id="c", document_id="d", title="A", score=0.0)))

    def test_missing_score_passes_as_undecidable(self):
        self.assertTrue(rag_client.meets_threshold(context(chunk_id="c", document_id="d", title="A", score=None)))


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

    def test_below_threshold_chunks_are_not_used_as_evidence(self):
        """통과·미달이 섞여 있어도 미달 조각은 근거가 되지 않는다."""
        contexts = [
            context(chunk_id="pass", document_id="d1", title="통과", score=0.41, rank=1),
            context(chunk_id="drop1", document_id="d2", title="미달", score=0.38, rank=2),
            context(chunk_id="drop2", document_id="d3", title="미달", score=0.30, rank=3),
        ]
        result = rag_client.EvidencePassthroughGenerator().invoke(self.request(contexts))
        self.assertEqual(result["used_chunk_ids"], ["pass"])

    def test_all_below_threshold_yields_no_evidence(self):
        contexts = [
            context(chunk_id="c1", document_id="d1", title="A", score=0.38),
            context(chunk_id="c2", document_id="d2", title="B", score=0.30),
        ]
        result = rag_client.EvidencePassthroughGenerator().invoke(self.request(contexts))
        self.assertEqual(result["used_chunk_ids"], [])

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


class HybridScoreTest(unittest.TestCase):
    """검색기가 하이브리드로 바뀌어도 화면이 모든 질문을 보류하지 않아야 한다.

    기준선 0.40은 코사인 유사도를 재서 정한 값이다. RRF 점수는 척도가 달라
    기본 가중치에서 이론상 최댓값이 2.5/61 ≈ 0.041뿐이므로,
    같은 값을 그대로 적용하면 어떤 조각도 통과하지 못한다.
    """

    RRF_CEILING = 2.5 / 61

    @classmethod
    def rrf(cls, chunk_id: str, document_id: str, *, rank: int = 1, score: float | None = None) -> dict:
        item = context(
            chunk_id=chunk_id,
            document_id=document_id,
            title=chunk_id,
            rank=rank,
            score=cls.RRF_CEILING if score is None else score,
        )
        item["score_type"] = "relevance"
        return item

    def test_rrf_ceiling_is_far_below_the_cosine_threshold(self):
        """전제 확인: 최고점 조각조차 기준선 숫자에는 닿지 못한다."""
        self.assertLess(self.RRF_CEILING, rag_client.TEMP_EVIDENCE_MIN_SCORE)

    def test_rrf_score_is_not_graded_against_the_cosine_threshold(self):
        self.assertFalse(rag_client.is_threshold_comparable(self.rrf("c1", "d1")))
        self.assertTrue(rag_client.meets_threshold(self.rrf("c1", "d1")))

    def test_cosine_score_is_still_graded(self):
        passing = context(chunk_id="c1", document_id="d1", title="A", score=0.44)
        failing = context(chunk_id="c2", document_id="d2", title="B", score=0.33)
        self.assertTrue(rag_client.is_threshold_comparable(passing))
        self.assertTrue(rag_client.meets_threshold(passing))
        self.assertFalse(rag_client.meets_threshold(failing))

    def test_missing_score_type_is_undecidable_and_passes(self):
        item = context(chunk_id="c1", document_id="d1", title="A", score=0.01)
        item.pop("score_type")
        self.assertTrue(rag_client.meets_threshold(item))

    def test_evidence_checker_does_not_hold_every_hybrid_answer(self):
        contexts = [self.rrf("c1", "d1"), self.rrf("c2", "d2", rank=2, score=0.0403)]
        self.assertEqual(rag_client.ScoreEvidenceChecker().decide("q", contexts), "sufficient")

    def test_generator_keeps_hybrid_contexts_as_evidence(self):
        contexts = [self.rrf("c1", "d1"), self.rrf("c2", "d2", rank=2, score=0.0403)]
        result = rag_client.EvidencePassthroughGenerator().invoke(GeneratorContractTest.request(contexts))
        self.assertEqual(result["candidate_response_type"], "answered")
        self.assertEqual(result["used_chunk_ids"], ["c1", "c2"])


class ThresholdDisplayTest(unittest.TestCase):
    """기준선을 적용하지 않은 결과에 기준선 숫자를 띄우면 틀린 설명이 된다."""

    def test_cosine_results_are_reported_as_graded(self):
        contexts = [context(chunk_id="c1", document_id="d1", title="A", score=0.44)]
        self.assertTrue(retrieval.threshold_applies(contexts))
        self.assertEqual(retrieval.score_label(contexts), "유사도")

    def test_hybrid_results_are_reported_as_ungraded(self):
        contexts = [HybridScoreTest.rrf("c1", "d1")]
        self.assertFalse(retrieval.threshold_applies(contexts))
        self.assertEqual(retrieval.score_label(contexts), "관련도")

    def test_no_contexts_is_ungraded(self):
        self.assertFalse(retrieval.threshold_applies([]))

class RetrievalModeTest(unittest.TestCase):
    """BM25 인덱스는 각자 만들어야 한다. 없다고 화면이 멈추면 안 된다."""

    def test_missing_index_falls_back_to_dense(self):
        absent = str(PROJECT_ROOT / "data" / "processed" / "없는파일.sqlite3")
        with mock.patch.dict(os.environ, {"AKS_BM25_INDEX_PATH": absent}):
            self.assertEqual(rag_client.retrieval_mode(), "dense")
            self.assertEqual(retrieval.retrieval_label(), "의미 검색 단독")

    def test_existing_index_selects_hybrid(self):
        present = str(Path(__file__).resolve())
        with mock.patch.dict(os.environ, {"AKS_BM25_INDEX_PATH": present}):
            self.assertEqual(rag_client.retrieval_mode(), "hybrid")
            self.assertIn("하이브리드", retrieval.retrieval_label())

    def test_override_wins_over_default_path(self):
        override = str(Path(__file__).resolve())
        with mock.patch.dict(os.environ, {"AKS_BM25_INDEX_PATH": override}):
            self.assertEqual(rag_client.bm25_index_path(), Path(override))

class CompoundQuestionTest(unittest.TestCase):
    """팀 합의(2026-09-01): 여러 질문은 나눠 답하지 않고 하나만 물어봐 달라고 되돌려준다."""

    SINGLE = [
        "경복궁에 대해 알려줘",
        "석굴암 본존불의 특징은?",
        "창덕궁과 덕수궁은 같은 궁궐이야?",
        "경주 불국사, 석굴암에 대해 알려줘",
    ]
    COMPOUND = [
        "경복궁이 뭐야? 창덕궁은 언제 지어졌어?",
        "경복궁의 건립 시기, 만든 사람, 주요 건물, 역사적 사건, 현재 위치를 알려줘",
    ]

    def test_single_questions_are_not_blocked(self):
        """멀쩡한 질문을 막는 쪽이 답을 못 주는 것보다 나쁘다."""
        for question in self.SINGLE:
            with self.subTest(question=question):
                self.assertFalse(rag_client.is_compound(question))

    def test_compound_questions_are_detected(self):
        for question in self.COMPOUND:
            with self.subTest(question=question):
                self.assertTrue(rag_client.is_compound(question))

    def test_separate_questions_become_options(self):
        parts = rag_client.split_questions("경복궁이 뭐야? 창덕궁은 언제 지어졌어?")
        self.assertEqual(parts, ["경복궁이 뭐야?", "창덕궁은 언제 지어졌어?"])

    def test_comma_list_offers_no_options(self):
        """주어가 빠진 조각은 혼자서 질문이 못 되므로 버튼으로 만들지 않는다."""
        question = "경복궁의 건립 시기, 만든 사람, 주요 건물, 역사적 사건, 현재 위치를 알려줘"
        self.assertEqual(rag_client.compound_clarification(question)["options"], [])

    def test_clarification_matches_contract_shape(self):
        clarification = rag_client.compound_clarification("경복궁이 뭐야? 창덕궁은?")
        self.assertEqual(set(clarification), {"reason_code", "question", "options"})
        self.assertLessEqual(len(clarification["options"]), 3)
        for option in clarification["options"]:
            self.assertEqual(set(option), {"id", "label", "source_chunk_ids"})

    def test_generator_returns_clarification_without_citing_evidence(self):
        contexts = [context(chunk_id="c1", document_id="d1", title="A")]
        request = GeneratorContractTest.request(contexts)
        request["question"] = "경복궁이 뭐야? 창덕궁은 언제 지어졌어?"
        result = rag_client.EvidencePassthroughGenerator().invoke(request)
        self.assertEqual(result["candidate_response_type"], "needs_clarification")
        # 계약: needs_clarification은 근거를 인용할 수 없다.
        self.assertEqual(result["used_chunk_ids"], [])
        self.assertIsNone(result["premise_correction"])
        self.assertEqual(result["related_topic_candidates"], [])

    def test_single_question_still_answers(self):
        contexts = [context(chunk_id="c1", document_id="d1", title="A")]
        request = GeneratorContractTest.request(contexts)
        request["question"] = "경복궁에 대해 알려줘"
        result = rag_client.EvidencePassthroughGenerator().invoke(request)
        self.assertEqual(result["candidate_response_type"], "answered")

if __name__ == "__main__":
    unittest.main()
