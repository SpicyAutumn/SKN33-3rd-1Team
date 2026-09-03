from __future__ import annotations

import json
import unittest

from rag_service.ollama_generator import (
    OllamaGenerator,
    _keep_alive_value,
    _normalize_corrected_premise,
    _repair_chunk_ids,
)


CONTEXT = {
    "chunk_id": "aks:E0002434:test:body:0001",
    "document_id": "E0002434",
    "title": "경복궁",
    "content": "경복궁은 1394년에 공사를 시작해 이듬해에 완성하였다.",
    "source_url": "https://example.test/E0002434",
    "section": "body",
    "retrieval_rank": 1,
    "retrieval_score": 0.9,
    "score_type": "similarity",
    "metadata": {
        "aliases": [],
        "document_fingerprint": "doc-fingerprint",
        "chunking_fingerprint": "chunk-fingerprint",
    },
}


def generation_request() -> dict:
    return {
        "schema_version": "0.3.0-draft",
        "request_id": "REQ-1",
        "interaction_id": "INT-1",
        "question": "경복궁은 언제 지어졌어?",
        "audience_level": "general",
        "response_language": "ko",
        "retrieved_contexts": [CONTEXT],
        "grounding_decision": "sufficient",
        "clarification_context": None,
    }


class OllamaGeneratorTest(unittest.TestCase):
    def test_invokes_non_thinking_json_chat_and_assembles_contract(self) -> None:
        captured: dict = {}

        def transport(url: str, payload: dict, timeout: float) -> dict:
            captured.update(url=url, payload=payload, timeout=timeout)
            return {
                "model": "qwen3:8b",
                "done_reason": "stop",
                "prompt_eval_count": 120,
                "eval_count": 30,
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "candidate_response_type": "answered",
                            "draft_message": "경복궁은 1395년에 완성되었습니다.",
                            "used_chunk_ids": ["CTX-1"],
                            "clarification": None,
                            "premise_correction": None,
                            "related_topic_candidates": [],
                        },
                        ensure_ascii=False,
                    ),
                },
            }

        generator = OllamaGenerator(
            base_url="https://pod.example/",
            model="qwen3:8b",
            transport=transport,
        )
        result = generator.invoke(generation_request())

        self.assertEqual(captured["url"], "https://pod.example/api/chat")
        self.assertFalse(captured["payload"]["think"])
        self.assertFalse(captured["payload"]["stream"])
        self.assertEqual(captured["payload"]["keep_alive"], "1h")
        self.assertEqual(
            captured["payload"]["format"]["properties"]["candidate_response_type"]["enum"][0],
            "answered",
        )
        self.assertEqual(captured["payload"]["options"]["temperature"], 0.0)
        self.assertEqual(captured["payload"]["options"]["num_predict"], 640)
        self.assertIn(CONTEXT["content"], captured["payload"]["messages"][1]["content"])
        self.assertIn('"context_ref":"CTX-1"', captured["payload"]["messages"][1]["content"])
        self.assertNotIn(CONTEXT["chunk_id"], captured["payload"]["messages"][1]["content"])
        self.assertIn("5~8개 문장", captured["payload"]["messages"][1]["content"])
        self.assertEqual(result["request_id"], "REQ-1")
        self.assertEqual(result["audience_level"], "general")
        self.assertEqual(result["used_chunk_ids"], [CONTEXT["chunk_id"]])
        self.assertEqual(result["generation_metadata"]["model_id"], "qwen3:8b")
        self.assertEqual(result["generation_metadata"]["token_usage"]["total_tokens"], 150)

    def test_restores_context_refs_in_nested_contract_fields(self) -> None:
        def transport(url: str, payload: dict, timeout: float) -> dict:
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "candidate_response_type": "corrected_premise",
                            "draft_message": "1394년에 완성된 것이 아니라 1395년에 완성되었습니다.",
                            "used_chunk_ids": [],
                            "clarification": None,
                            "premise_correction": {
                                "original_premise": "1394년에 완성",
                                "corrected_premise": "1395년에 완성",
                                "source_chunk_ids": ["CTX-1"],
                            },
                            "related_topic_candidates": [],
                        },
                        ensure_ascii=False,
                    )
                }
            }

        result = OllamaGenerator(
            base_url="https://pod.example",
            transport=transport,
        ).invoke(generation_request())

        self.assertEqual(
            result["premise_correction"]["source_chunk_ids"],
            [CONTEXT["chunk_id"]],
        )

    def test_keeps_unknown_context_ref_for_service_validation(self) -> None:
        output = {
            "candidate_response_type": "answered",
            "draft_message": "답변",
            "used_chunk_ids": ["CTX-999"],
            "clarification": None,
            "premise_correction": None,
            "related_topic_candidates": [],
        }
        restored = OllamaGenerator._restore_context_ids(output, {"CTX-1": CONTEXT["chunk_id"]})
        self.assertEqual(restored["used_chunk_ids"], ["CTX-999"])

    def test_keep_alive_can_be_overridden(self) -> None:
        captured: dict = {}

        def transport(url: str, payload: dict, timeout: float) -> dict:
            captured.update(payload=payload)
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "candidate_response_type": "answered",
                            "draft_message": "근거 기반 답변",
                            "used_chunk_ids": [CONTEXT["chunk_id"]],
                            "clarification": None,
                            "premise_correction": None,
                            "related_topic_candidates": [],
                        },
                        ensure_ascii=False,
                    )
                }
            }

        OllamaGenerator(
            base_url="https://pod.example",
            keep_alive="30m",
            transport=transport,
        ).invoke(generation_request())
        self.assertEqual(captured["payload"]["keep_alive"], "30m")

    def test_keep_alive_without_unit_is_sent_as_a_number(self) -> None:
        """Ollama는 문자열 keep_alive를 Go duration으로 읽어 단위를 요구한다.

        `-1`은 "계속 올려 둔다"는 뜻으로 문서에 나오는 값인데, 문자열로 보내면
        `time: missing unit in duration "-1"`으로 400이 떨어진다.
        """
        self.assertEqual(_keep_alive_value("-1"), -1)
        self.assertEqual(_keep_alive_value("3600"), 3600)
        self.assertEqual(_keep_alive_value("1h"), "1h")
        self.assertEqual(_keep_alive_value("30m"), "30m")
        self.assertEqual(_keep_alive_value(""), "1h")
        self.assertEqual(_keep_alive_value(None), "1h")

    def test_rejects_output_with_contract_fields_missing(self) -> None:
        def transport(url: str, payload: dict, timeout: float) -> dict:
            return {"message": {"content": '{"draft_message":"불완전"}'}}

        generator = OllamaGenerator(base_url="https://pod.example", transport=transport)
        with self.assertRaisesRegex(ValueError, "generation contract"):
            generator.invoke(generation_request())

    def test_discards_related_topics_while_mvp_feature_is_disabled(self) -> None:
        def transport(url: str, payload: dict, timeout: float) -> dict:
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "candidate_response_type": "answered",
                            "draft_message": "근거 기반 답변",
                            "used_chunk_ids": [CONTEXT["chunk_id"]],
                            "clarification": None,
                            "premise_correction": None,
                            "related_topic_candidates": ["계약에 맞지 않는 문자열 후보"],
                        },
                        ensure_ascii=False,
                    )
                }
            }

        generator = OllamaGenerator(base_url="https://pod.example", transport=transport)
        result = generator.invoke(generation_request())
        self.assertEqual(result["related_topic_candidates"], [])

    def test_requires_base_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "OLLAMA_BASE_URL"):
            OllamaGenerator(base_url="", model="qwen3:8b")

    def test_easy_and_advanced_requests_receive_distinct_profiles(self) -> None:
        easy_request = generation_request()
        easy_request["audience_level"] = "easy"
        advanced_request = generation_request()
        advanced_request["audience_level"] = "advanced"

        easy_prompt = OllamaGenerator._request_prompt(easy_request)
        advanced_prompt = OllamaGenerator._request_prompt(advanced_request)

        self.assertIn("초등학생", easy_prompt)
        self.assertIn("3~5개의 짧은 문장", easy_prompt)
        self.assertIn("정궁은 '왕이 주로 머물며 나라 일을 보던 중심 궁궐'", easy_prompt)
        self.assertIn("10~16개 문장", advanced_prompt)
        self.assertIn("연도·인물·제도·건물·사건", advanced_prompt)
        self.assertIn("서로 다른 인물의 행동을 합치지 않는다", advanced_prompt)


if __name__ == "__main__":
    unittest.main()


class ChunkIdRepairTest(unittest.TestCase):
    """모델이 chunk_id를 잘라서 돌려주는 것을 제자리로 되돌린다.

    exaone은 없는 id를 지어내지 않는다. 있는 id를 자른다. 실측한 두 가지다.

        끝을 자름    aks:E0052934:d1f5f9f8a52c
        가운데를 뺌  aks:E0047404:body:0014

    되돌리지 않으면 RagService가 `unknown chunk_id`로 전체 답변을 죽인다.
    근거를 많이 줄수록 자주 틀리므로, 깊이 있게(top_k=8)에서 특히 잘 난다.
    """

    ALLOWED = [
        "aks:E0052934:d1f5f9f8a52c:definition:0001",
        "aks:E0047404:1a2b3c4d5e6f:body:0014",
    ]

    def repair(self, output: dict) -> dict:
        _repair_chunk_ids(output, list(self.ALLOWED))
        return output

    def test_exact_ids_are_kept(self):
        out = self.repair({"candidate_response_type": "answered", "used_chunk_ids": [self.ALLOWED[0]]})
        self.assertEqual(out["used_chunk_ids"], [self.ALLOWED[0]])

    def test_truncated_tail_is_restored(self):
        out = self.repair(
            {"candidate_response_type": "answered", "used_chunk_ids": ["aks:E0052934:d1f5f9f8a52c"]}
        )
        self.assertEqual(out["used_chunk_ids"], [self.ALLOWED[0]])

    def test_missing_hash_segment_is_restored(self):
        out = self.repair(
            {"candidate_response_type": "answered", "used_chunk_ids": ["aks:E0047404:body:0014"]}
        )
        self.assertEqual(out["used_chunk_ids"], [self.ALLOWED[1]])

    def test_ambiguous_prefix_is_dropped(self):
        """두 조각이 같은 문서에서 나오면 접두사만으로는 무엇인지 알 수 없다."""
        allowed = ["aks:E1:aaaaaaaaaaaa:body:0001", "aks:E1:aaaaaaaaaaaa:body:0002"]
        out = {"candidate_response_type": "answered", "used_chunk_ids": ["aks:E1"]}
        _repair_chunk_ids(out, allowed)
        self.assertEqual(out["used_chunk_ids"], [])

    def test_answered_without_any_usable_evidence_becomes_insufficient(self):
        """근거 없는 답변은 내보내지 않는다. 그대로 두면 RagService가 죽는다."""
        out = self.repair({"candidate_response_type": "answered", "used_chunk_ids": ["없는거"]})
        self.assertEqual(out["candidate_response_type"], "insufficient_evidence")
        self.assertEqual(out["used_chunk_ids"], [])
        self.assertTrue(out["draft_message"].strip())

    def test_answered_with_empty_citations_becomes_insufficient(self):
        out = self.repair({"candidate_response_type": "answered", "used_chunk_ids": []})
        self.assertEqual(out["candidate_response_type"], "insufficient_evidence")

    def test_non_answer_types_must_not_cite(self):
        """계약상 답변이 아닌 응답은 근거를 인용할 수 없다."""
        for response_type in ("insufficient_evidence", "safety_refusal", "out_of_scope"):
            with self.subTest(response_type=response_type):
                out = self.repair(
                    {"candidate_response_type": response_type, "used_chunk_ids": [self.ALLOWED[0]]}
                )
                self.assertEqual(out["used_chunk_ids"], [])

    def test_nested_evidence_fields_are_repaired_too(self):
        """RagService는 used_chunk_ids만 보지 않는다. 한 곳만 고치면 다른 곳에서 죽는다."""
        out = self.repair(
            {
                "candidate_response_type": "answered",
                "used_chunk_ids": [self.ALLOWED[0]],
                "premise_correction": {"source_chunk_ids": ["aks:E0047404:body:0014"]},
                "clarification": {"options": [{"source_chunk_ids": ["aks:E0052934:d1f5f9f8a52c"]}]},
                "related_topic_candidates": [{"source_chunk_ids": ["없는거"]}],
            }
        )
        self.assertEqual(out["premise_correction"]["source_chunk_ids"], [self.ALLOWED[1]])
        self.assertEqual(out["clarification"]["options"][0]["source_chunk_ids"], [self.ALLOWED[0]])
        self.assertEqual(out["related_topic_candidates"][0]["source_chunk_ids"], [])


class ResponseTypeNormalizationTest(unittest.TestCase):
    def test_answer_that_explicitly_corrects_assertion_becomes_corrected_premise(self):
        output = {
            "candidate_response_type": "answered",
            "draft_message": "길쌈노래는 민요이며 판소리와는 다른 장르로 분류됩니다.",
            "used_chunk_ids": [CONTEXT["chunk_id"]],
            "clarification": None,
            "premise_correction": None,
            "related_topic_candidates": [],
        }

        _normalize_corrected_premise(output, "길쌈노래는 판소리 작품이지?")

        self.assertEqual(output["candidate_response_type"], "corrected_premise")
        self.assertEqual(
            output["premise_correction"]["source_chunk_ids"],
            [CONTEXT["chunk_id"]],
        )

    def test_answer_that_states_question_year_was_wrong_becomes_corrected_premise(self):
        output = {
            "candidate_response_type": "answered",
            "draft_message": (
                "지봉유설은 1614년에 편찬한 책입니다. "
                "질문에서 언급된 연도가 1615년으로 되어 있지만 실제 편찬 연도는 1614년입니다."
            ),
            "used_chunk_ids": [CONTEXT["chunk_id"]],
            "clarification": None,
            "premise_correction": None,
            "related_topic_candidates": [],
        }

        _normalize_corrected_premise(output, "지봉유설은 1615년에 편찬한 책이지?")

        self.assertEqual(output["candidate_response_type"], "corrected_premise")
        self.assertFalse(output["draft_message"].startswith("네, 맞습니다"))
        self.assertEqual(
            output["premise_correction"]["corrected_premise"],
            "지봉유설은 1614년에 편찬한 책입니다.",
        )

    def test_valid_correction_detail_overrides_inconsistent_insufficient_type(self):
        output = {
            "candidate_response_type": "insufficient_evidence",
            "draft_message": "상대별곡의 작자는 이색이 아니라 권근입니다.",
            "used_chunk_ids": [],
            "clarification": None,
            "premise_correction": {
                "original_premise": "이색이 지음",
                "corrected_premise": "권근이 지음",
                "source_chunk_ids": [CONTEXT["chunk_id"]],
            },
            "related_topic_candidates": [],
        }

        _normalize_corrected_premise(output, "상대별곡은 이색이 지은 경기체가 맞지?")

        self.assertEqual(output["candidate_response_type"], "corrected_premise")
        self.assertIsNotNone(output["premise_correction"])

    def test_insufficient_label_with_explicit_correction_and_evidence_is_promoted(self):
        output = {
            "candidate_response_type": "insufficient_evidence",
            "draft_message": "상대별곡은 이색이 아닌 권근이 지은 경기체가로 확인됩니다.",
            "used_chunk_ids": [CONTEXT["chunk_id"]],
            "clarification": None,
            "premise_correction": None,
            "related_topic_candidates": [],
        }

        _normalize_corrected_premise(output, "상대별곡은 이색이 지은 경기체가 맞지?")

        self.assertEqual(output["candidate_response_type"], "corrected_premise")
        self.assertEqual(
            output["premise_correction"]["source_chunk_ids"],
            [CONTEXT["chunk_id"]],
        )

    def test_non_answer_clears_incompatible_detail_fields(self):
        output = {
            "candidate_response_type": "insufficient_evidence",
            "draft_message": "근거가 부족합니다.",
            "used_chunk_ids": [],
            "clarification": {"reason_code": "wrong", "question": "질문", "options": []},
            "premise_correction": {"source_chunk_ids": []},
            "related_topic_candidates": [],
        }

        _normalize_corrected_premise(output, "질문")

        self.assertIsNone(output["clarification"])
        self.assertIsNone(output["premise_correction"])

    def test_plain_answer_with_negative_sentence_is_not_reclassified(self):
        output = {
            "candidate_response_type": "answered",
            "draft_message": "경복궁은 서울에 있으며 다른 지역의 궁궐이 아닙니다.",
            "used_chunk_ids": [CONTEXT["chunk_id"]],
            "clarification": None,
            "premise_correction": None,
            "related_topic_candidates": [],
        }

        _normalize_corrected_premise(output, "경복궁은 어디에 있어?")

        self.assertEqual(output["candidate_response_type"], "answered")
        self.assertIsNone(output["premise_correction"])
