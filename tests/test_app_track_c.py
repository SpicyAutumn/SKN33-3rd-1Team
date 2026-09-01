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
from tabs.chat import _reusable_contexts  # noqa: E402
import heritage_graph  # noqa: E402
from tabs.evaluation import ANSWER_METRICS  # noqa: E402


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
    """팀 결정(2026-09-01): 근거 선택에 문서당 제한을 두지 않는다."""

    def test_keeps_same_document_chunks_in_search_order(self):
        picked = rag_client.pick_evidence(
            [
                context(chunk_id="c1", document_id="d1", title="A", rank=1),
                context(chunk_id="c2", document_id="d1", title="A", rank=2),
                context(chunk_id="c3", document_id="d2", title="B", rank=3),
                context(chunk_id="c4", document_id="d3", title="C", rank=4),
            ],
            limit=3,
        )
        self.assertEqual([p["chunk_id"] for p in picked], ["c1", "c2", "c3"])

    def test_same_chunk_is_not_repeated(self):
        picked = rag_client.pick_evidence(
            [
                context(chunk_id="c1", document_id="d1", title="A", rank=1),
                context(chunk_id="c1", document_id="d1", title="A", rank=2),
            ]
        )
        self.assertEqual(len(picked), 1)


class EvidenceCheckerTest(unittest.TestCase):
    """점수 기준선은 쓰지 않는다. 판단은 근거를 읽는 생성기에 맡긴다."""

    def setUp(self):
        self.checker = rag_client.ContentEvidenceChecker()

    def test_low_score_still_passes(self):
        contexts = [context(chunk_id="c1", document_id="d1", title="A", score=0.01)]
        self.assertEqual(self.checker.decide("q", contexts), "sufficient")

    def test_missing_score_passes(self):
        contexts = [context(chunk_id="c1", document_id="d1", title="A", score=None)]
        self.assertEqual(self.checker.decide("q", contexts), "sufficient")

    def test_blank_content_is_insufficient(self):
        contexts = [context(chunk_id="c1", document_id="d1", title="A", content="   ")]
        self.assertEqual(self.checker.decide("q", contexts), "insufficient")

    def test_no_contexts_is_insufficient(self):
        self.assertEqual(self.checker.decide("q", []), "insufficient")

    def test_second_ask_defers_to_the_generator(self):
        """RagService는 생성기가 근거 부족이라고 했을 때만 다시 물어본다.

        늘 통과시키면 서비스가 불일치를 오류로 보고 예외를 던진다.
        범위 밖 질문에서는 반드시 그렇게 된다.
        """
        contexts = [context(chunk_id="c1", document_id="d1", title="A")]
        self.assertEqual(self.checker.decide("아이폰 가격", contexts), "sufficient")
        self.assertEqual(self.checker.decide("아이폰 가격", contexts), "insufficient")

    def test_a_different_question_starts_over(self):
        contexts = [context(chunk_id="c1", document_id="d1", title="A")]
        self.checker.decide("아이폰 가격", contexts)
        self.assertEqual(self.checker.decide("경복궁에 대해 알려줘", contexts), "sufficient")

    def test_the_next_question_is_not_blocked_by_the_previous_one(self):
        contexts = [context(chunk_id="c1", document_id="d1", title="A")]
        self.checker.decide("아이폰 가격", contexts)
        self.checker.decide("아이폰 가격", contexts)
        self.assertEqual(self.checker.decide("아이폰 가격", contexts), "sufficient")


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

    def test_low_score_chunks_are_still_used(self):
        """점수 기준선을 두지 않는다. 검색이 올린 조각을 화면 직전에 버리지 않는다."""
        contexts = [
            context(chunk_id="c1", document_id="d1", title="A", score=0.41, rank=1),
            context(chunk_id="c2", document_id="d2", title="B", score=0.38, rank=2),
            context(chunk_id="c3", document_id="d3", title="C", score=0.30, rank=3),
        ]
        result = rag_client.EvidencePassthroughGenerator().invoke(self.request(contexts))
        self.assertEqual(result["used_chunk_ids"], ["c1", "c2", "c3"])

    def test_same_document_chunks_are_all_used(self):
        """팀 결정: 문서당 제한 없음. 같은 문서의 여러 청크가 필요한 질문이 있다."""
        contexts = [
            context(chunk_id="c1", document_id="d1", title="경복궁", rank=1),
            context(chunk_id="c2", document_id="d1", title="경복궁", rank=2),
            context(chunk_id="c3", document_id="d1", title="경복궁", rank=3),
        ]
        result = rag_client.EvidencePassthroughGenerator().invoke(self.request(contexts))
        self.assertEqual(result["used_chunk_ids"], ["c1", "c2", "c3"])

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


class HeritageGraphTest(unittest.TestCase):
    """탐험 지도는 만든 목록 전체를 재료로 쓴다. 검색 결과 3건이 아니다."""

    @classmethod
    def setUpClass(cls):
        cls.book = heritage_graph.catalog()

    def test_catalog_covers_the_whole_corpus(self):
        self.assertGreater(len(self.book.entries), 70_000)

    def test_top_level_folds_sub_periods(self):
        self.assertEqual(heritage_graph.top_level("조선/조선 전기"), "조선")
        self.assertEqual(heritage_graph.top_level("조선/조선 전기 | 조선/조선 후기"), "조선")
        self.assertEqual(heritage_graph.top_level(""), "")

    def test_lookup_by_title_and_document_id(self):
        entry = self.book.find("경복궁")
        self.assertIsNotNone(entry)
        self.assertEqual(self.book.find(entry.document_id).title, "경복궁")

    def test_parts_are_found_by_title_prefix(self):
        titles = {e.title for e in self.book.titles_starting_with("경복궁")}
        self.assertIn("경복궁 경회루", titles)
        self.assertNotIn("경복궁", titles)

    def test_region_comes_from_the_title(self):
        self.assertEqual(self.book.find("강릉 오죽헌").region, "강릉")

    def test_map_without_search_still_has_branches(self):
        """검색 연결이 없어도 만든 목록만으로 그릴 수 있는 가지는 남는다."""
        payload = heritage_graph.build_map("경복궁", neighbors=None)
        self.assertEqual(payload["root"]["title"], "경복궁")
        titles = [b["title"] for b in payload["branches"]]
        self.assertIn("딸린 유산", titles)

    def test_unknown_root_returns_none(self):
        self.assertIsNone(heritage_graph.build_map("없는유산", neighbors=None))

    def test_only_heritage_types_are_recommended(self):
        """`궁궐`을 뿌리로 두면 `영`·`장`·`서` 같은 한문학 개념이 올라왔었다."""
        payload = heritage_graph.build_map("궁궐", neighbors=None)
        for branch in payload["branches"]:
            for node in branch["nodes"]:
                entry = self.book.by_document[node["document_id"]]
                with self.subTest(title=node["title"]):
                    self.assertTrue(self.book.is_heritage(entry))

    def test_heritage_values_leave_out_people_and_concepts(self):
        values = self.book.heritage_type_values()
        tops = {heritage_graph.top_level(v) for v in values}
        self.assertTrue(tops.issubset(set(heritage_graph.HERITAGE_TYPES)))
        self.assertNotIn("인물", tops)
        self.assertNotIn("개념", tops)

    def test_excluding_a_kind_drops_it(self):
        values = self.book.heritage_type_values(exclude_top_level="유적")
        self.assertNotIn("유적", {heritage_graph.top_level(v) for v in values})

    def test_unknown_period_makes_no_branch(self):
        """`미상`은 6,586건이 함께 달고 있어 같은 값이라는 사실이 아무것도 설명하지 못한다."""
        self.assertEqual(heritage_graph.top_level(self.book.find("궁궐").period), "미상")
        payload = heritage_graph.build_map("궁궐", neighbors=None)
        self.assertFalse([b for b in payload["branches"] if b["title"].startswith("시대 :")])

    def test_root_prefers_a_heritage_item_over_a_concept(self):
        """`직지`를 물으면 검색 1위가 `직`(유교 개념)이고 정답은 2위였다."""
        contexts = [
            {"document_id": self.book.find("직").document_id, "title": "직", "retrieval_rank": 1},
            {
                "document_id": self.book.find("불조직지심체요절").document_id,
                "title": "불조직지심체요절",
                "retrieval_rank": 2,
            },
        ]
        self.assertEqual(self.book.resolve(contexts, "직지").title, "불조직지심체요절")

    def test_root_prefers_the_document_with_more_chunks(self):
        """`거북선에 대해 알려줘`는 1위가 `거북점`이었다. 둘 다 문화유산이다."""
        turtle = self.book.find("거북선").document_id
        divination = self.book.find("거북점").document_id
        contexts = [
            {"document_id": divination, "title": "거북점", "retrieval_rank": 1},
            {"document_id": turtle, "title": "거북선", "retrieval_rank": 2},
            {"document_id": turtle, "title": "거북선", "retrieval_rank": 3},
        ]
        self.assertEqual(self.book.resolve(contexts, "거북선에 대해 알려줘").title, "거북선")

    def test_no_usable_context_gives_no_root(self):
        self.assertIsNone(self.book.resolve([{"document_id": "없음", "title": "없음"}], "질문"))

    def test_region_comes_from_the_address_when_the_title_has_none(self):
        """제목으로 지역이 잡히는 항목은 9.6%뿐이다. `경복궁`도 그중에 없다."""
        self.assertEqual(self.book.find("경복궁").region, "")
        self.assertEqual(
            heritage_graph.region_from_summary("서울특별시 종로구 세종로에 있는 궁궐."), "서울"
        )
        self.assertEqual(
            heritage_graph.region_from_summary("경상북도 경주시 진현동에 있다."), "경주"
        )
        self.assertEqual(heritage_graph.region_from_summary("조선 후기의 문신이다."), "")

    def test_same_title_is_not_repeated(self):
        """`경주`나 `훈민정음`처럼 이름이 겹치는 문서가 여럿 있다."""
        payload = heritage_graph.build_map("훈민정음", neighbors=None)
        titles = [n["title"] for b in payload["branches"] for n in b["nodes"]]
        self.assertEqual(len(titles), len(set(titles)))
        self.assertNotIn("훈민정음", titles)


class HybridSimilarityTest(unittest.TestCase):
    """순위는 하이브리드가 정하고, 점수는 유사도를 그대로 보여 준다."""

    META = {"aliases": [], "document_fingerprint": "fp", "chunking_fingerprint": "cf"}

    class FakeDense:
        def __init__(self, outer):
            self.outer = outer

        def search(self, question, *, top_k=5):
            order = [("c3", 0.51), ("c1", 0.44), ("c2", 0.39)]
            return [
                {
                    "chunk_id": cid, "document_id": cid, "title": cid, "content": "본문",
                    "source_url": "https://x", "section": "body", "retrieval_rank": rank,
                    "retrieval_score": score, "score_type": "similarity",
                    "metadata": dict(self.outer.META),
                }
                for rank, (cid, score) in enumerate(order, start=1)
            ][:top_k]

    class FakeBM25:
        def __init__(self, outer):
            self.outer = outer

        def search(self, question, *, top_k=5):
            # 낱말 검색은 c1을 1위로 올린다. 융합하면 c1이 앞으로 나와야 한다.
            order = ["c1", "c1x", "c3"]
            return [
                {
                    "chunk_id": cid, "document_id": cid, "title": cid, "content": "본문",
                    "source_url": "https://x", "section": "body", "retrieval_rank": rank,
                    "retrieval_score": 9.0 - rank, "score_type": "relevance",
                    "metadata": dict(self.outer.META),
                }
                for rank, cid in enumerate(order, start=1)
            ][:top_k]

    def setUp(self):
        self.retriever = rag_client.HybridWithSimilarity(self.FakeDense(self), self.FakeBM25(self))

    def test_scores_are_cosine_similarity_not_rrf(self):
        results = self.retriever.search("질문", top_k=3)
        by_id = {r["chunk_id"]: r for r in results}
        self.assertEqual(by_id["c1"]["retrieval_score"], 0.44)
        self.assertEqual(by_id["c1"]["score_type"], "similarity")
        # RRF 점수(최댓값 약 0.041)가 새어 나오면 안 된다.
        for result in results:
            score = result["retrieval_score"]
            if score is not None:
                self.assertGreater(score, 0.1)

    def test_ranking_still_comes_from_hybrid(self):
        results = self.retriever.search("질문", top_k=3)
        self.assertEqual(results[0]["chunk_id"], "c1")
        self.assertEqual([r["retrieval_rank"] for r in results], [1, 2, 3])

    def test_bm25_only_chunk_has_no_similarity(self):
        """유사도를 잰 적이 없으면 계약대로 unknown으로 둔다."""
        results = self.retriever.search("질문", top_k=4)
        extra = [r for r in results if r["chunk_id"] == "c1x"]
        self.assertTrue(extra)
        self.assertIsNone(extra[0]["retrieval_score"])
        self.assertEqual(extra[0]["score_type"], "unknown")


class ScoreDisplayTest(unittest.TestCase):
    def test_similarity_is_shown_to_three_places(self):
        self.assertEqual(retrieval.format_score(0.4412), "0.441")

    def test_unmeasured_similarity_is_blank_not_zero(self):
        self.assertEqual(retrieval.format_score(None), "—")

    def test_hybrid_marks_the_score_as_reference_only(self):
        """1위 숫자가 2·3위보다 낮아 보일 수 있으므로 참고값이라고 밝힌다."""
        present = str(Path(__file__).resolve())
        with mock.patch.dict(os.environ, {"AKS_BM25_INDEX_PATH": present}):
            self.assertTrue(retrieval.score_is_reference_only())
            self.assertIn("참고값", retrieval.score_caption())

    def test_dense_only_keeps_the_plain_explanation(self):
        absent = str(PROJECT_ROOT / "data" / "processed" / "없는파일.sqlite3")
        with mock.patch.dict(os.environ, {"AKS_BM25_INDEX_PATH": absent}):
            self.assertFalse(retrieval.score_is_reference_only())
            self.assertNotIn("참고값", retrieval.score_caption())


class RetrievalReuseTest(unittest.TestCase):
    def tearDown(self):
        retrieval.get_service.cache_clear()

    def test_service_is_built_only_once(self):
        service = object()
        with mock.patch.object(retrieval.rag_client, "build_service", return_value=service) as build:
            self.assertIs(retrieval.get_service(), service)
            self.assertIs(retrieval.get_service(), service)
        build.assert_called_once_with()

    def test_fixed_context_retriever_skips_search_and_returns_a_copy(self):
        contexts = [context(chunk_id="c1", document_id="d1", title="경복궁")]
        retriever = retrieval._FixedContextsRetriever(contexts)

        first = retriever.search("경복궁을 쉽게 설명해줘", top_k=3)
        first[0]["title"] = "변경됨"
        second = retriever.search("경복궁을 자세히 설명해줘", top_k=3)

        self.assertEqual(second[0]["title"], "경복궁")
        self.assertIsNot(first, second)

    def test_same_question_reuses_nonempty_contexts(self):
        contexts = [context(chunk_id="c1", document_id="d1", title="경복궁")]
        last_result = {"question": "경복궁이 뭐야?", "retrieved_contexts": contexts}
        self.assertIs(_reusable_contexts(last_result, "경복궁이 뭐야?"), contexts)

    def test_different_question_or_empty_result_runs_a_new_search(self):
        last_result = {"question": "경복궁이 뭐야?", "retrieved_contexts": []}
        self.assertIsNone(_reusable_contexts(last_result, "창덕궁이 뭐야?"))
        self.assertIsNone(_reusable_contexts(last_result, "경복궁이 뭐야?"))


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

class EnvPlaceholderTest(unittest.TestCase):
    """`.env.example`을 복사만 하고 값을 안 바꾼 경우를 잡는다."""

    def test_placeholder_counts_as_missing(self):
        with mock.patch.dict(os.environ, {"OLLAMA_BASE_URL": "{{your_ollama_base_url}}"}):
            self.assertIn("OLLAMA_BASE_URL", rag_client.missing_env())

    def test_blank_counts_as_missing(self):
        with mock.patch.dict(os.environ, {"OLLAMA_BASE_URL": "   "}):
            self.assertIn("OLLAMA_BASE_URL", rag_client.missing_env())

    def test_real_value_passes(self):
        with mock.patch.dict(os.environ, {"OLLAMA_BASE_URL": "https://abc-11434.proxy.runpod.net"}):
            self.assertNotIn("OLLAMA_BASE_URL", rag_client.missing_env())

class ScopeCheckerTest(unittest.TestCase):
    """범위 판정은 근거 충분성과 다른 문제다. 점수로는 걸러지지 않는다."""

    OUT = [
        "현대자동차 주가 알려",      # 현대자동차㈜는 백과사전에 있다. 주가가 없을 뿐이다.
        "오늘 서울 날씨 어때",        # 서울특별시 항목의 기후 설명으로 오늘 날씨를 지어냈다.
        "비트코인 시세",
        "파이썬 for문 예제 알려줘",
        "강남 맛집 추천",
        "이 문장 번역해줘",
    ]
    IN = [
        "경복궁에 대해 알려줘",
        "석굴암 본존불의 특징은?",
        "훈민정음은 무엇인가요?",
        "측우기는 어떻게 날씨를 재나요?",       # `날씨`가 들어가도 지금을 묻지 않는다
        "조선시대 날씨 기록은 어떻게 남겼나요?",
        "조선시대 쌀 가격은 어땠나요?",         # `가격`도 마찬가지다
    ]

    def setUp(self):
        self.checker = rag_client.TopicScopeChecker()

    def test_questions_the_source_can_never_answer_are_blocked(self):
        for question in self.OUT:
            with self.subTest(question=question):
                self.assertFalse(self.checker.is_in_scope(question))

    def test_heritage_questions_pass(self):
        for question in self.IN:
            with self.subTest(question=question):
                self.assertTrue(self.checker.is_in_scope(question))

    def test_live_words_alone_do_not_block(self):
        """`날씨`가 들어갔다고 막으면 측우기 질문을 막게 된다."""
        self.assertTrue(self.checker.is_in_scope("조선의 날씨 관측 기구"))
        self.assertFalse(self.checker.is_in_scope("지금 날씨"))

    def test_empty_question_is_not_blocked_here(self):
        """빈 질문은 RagService가 먼저 거른다. 범위 판정이 대신 막지 않는다."""
        self.assertTrue(self.checker.is_in_scope(""))

class AnswerMetricsTest(unittest.TestCase):
    """평가 탭에는 답변 층 지표만 둔다 (PR #28)."""

    def test_only_answer_layer_metrics_are_shown(self):
        self.assertEqual(list(ANSWER_METRICS), ["faithfulness", "answer_relevancy"])

    def test_retrieval_layer_metrics_are_not_shown(self):
        """정답 라벨이 있어야 계산되는 지표다. 임의 질문에서는 늘 평가 불가로 남는다."""
        self.assertNotIn("context_precision", ANSWER_METRICS)
        self.assertNotIn("context_recall", ANSWER_METRICS)

    def test_each_metric_explains_itself(self):
        for name, detail in ANSWER_METRICS.items():
            with self.subTest(metric=name):
                self.assertEqual(set(detail), {"title", "short", "definition", "improvement"})
                self.assertTrue(all(str(v).strip() for v in detail.values()))

if __name__ == "__main__":
    unittest.main()
