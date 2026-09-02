from __future__ import annotations

import json
import unittest

from rag_service.ollama_generator import OllamaGenerator, _keep_alive_value


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
                            "used_chunk_ids": [CONTEXT["chunk_id"]],
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
        self.assertIn("5~8개 문장", captured["payload"]["messages"][1]["content"])
        self.assertEqual(result["request_id"], "REQ-1")
        self.assertEqual(result["audience_level"], "general")
        self.assertEqual(result["used_chunk_ids"], [CONTEXT["chunk_id"]])
        self.assertEqual(result["generation_metadata"]["model_id"], "qwen3:8b")
        self.assertEqual(result["generation_metadata"]["token_usage"]["total_tokens"], 150)

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
