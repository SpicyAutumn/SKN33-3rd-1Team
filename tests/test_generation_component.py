from __future__ import annotations

import json
import unittest

from generation import PROMPT_VERSION, PromptBaselineGenerator, build_messages
from rag_service import RagService, RagServiceError


CHUNK_ID = "aks:E0008547:test:definition:0001"
CONTEXT = {
    "chunk_id": CHUNK_ID,
    "document_id": "aks:E0008547",
    "title": "길쌈노래",
    "content": "여성들이 길쌈을 하면서 부르는 민요.",
    "source_url": "https://encykorea.aks.ac.kr/Article/E0008547",
    "section": "definition",
    "retrieval_rank": 1,
    "retrieval_score": 0.66,
    "score_type": "similarity",
    "metadata": {
        "aliases": ["길쌈노동요"],
        "document_fingerprint": "sha256:test",
        "chunking_fingerprint": None,
    },
}


def make_request() -> dict[str, object]:
    return {
        "schema_version": "0.3.0-draft",
        "request_id": "REQ-test",
        "interaction_id": "INT-test",
        "question": "길쌈노래를 쉽게 설명해줘",
        "audience_level": "easy",
        "response_language": "ko",
        "retrieved_contexts": [CONTEXT],
        "grounding_decision": "sufficient",
        "clarification_context": None,
    }


def answered_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "candidate_response_type": "answered",
        "draft_message": "길쌈노래는 여성들이 길쌈을 하며 부르던 민요입니다.",
        "used_chunk_ids": [CHUNK_ID],
        "clarification": None,
        "premise_correction": None,
        "related_topic_candidates": [],
    }
    payload.update(changes)
    return payload


class FakeResponse:
    def __init__(self, payload: object, *, raw: bool = False) -> None:
        self.content = payload if raw else json.dumps(payload, ensure_ascii=False)
        self.response_metadata = {"finish_reason": "stop"}
        self.usage_metadata = {"input_tokens": 120, "output_tokens": 35, "total_tokens": 155}


class FakeChatModel:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.messages: list[dict[str, str]] | None = None

    def invoke(self, messages: list[dict[str, str]]) -> FakeResponse:
        self.messages = messages
        return self.response


class FakeRetriever:
    def search(self, question: str, *, top_k: int = 3) -> list[dict[str, object]]:
        return [CONTEXT][:top_k]


class FakeEvidenceChecker:
    def decide(self, question: str, contexts: list[dict[str, object]]) -> str:
        return "sufficient"


class PromptBaselineGeneratorTest(unittest.TestCase):
    def make_generator(self, payload: object, *, raw: bool = False) -> tuple[PromptBaselineGenerator, FakeChatModel]:
        model = FakeChatModel(FakeResponse(payload, raw=raw))
        generator = PromptBaselineGenerator(model, model_id="test-chat-model", temperature=0.0)
        return generator, model

    def test_build_messages_serializes_context_as_json(self) -> None:
        messages = build_messages(make_request())

        self.assertEqual([message["role"] for message in messages], ["system", "user"])
        self.assertIn('"chunk_id": "aks:E0008547:test:definition:0001"', messages[1]["content"])
        self.assertIn("[CLARIFICATION_CONTEXT]\nnull", messages[1]["content"])
        self.assertNotIn("'chunk_id'", messages[1]["content"])

    def test_invoke_assembles_generation_result_and_runtime_metadata(self) -> None:
        generator, model = self.make_generator(answered_payload())

        result = generator.invoke(make_request())

        self.assertEqual(result["schema_version"], "0.3.0-draft")
        self.assertEqual(result["request_id"], "REQ-test")
        self.assertEqual(result["candidate_response_type"], "answered")
        self.assertEqual(result["audience_level"], "easy")
        self.assertEqual(result["used_chunk_ids"], [CHUNK_ID])
        self.assertEqual(result["generation_metadata"]["prompt_version"], PROMPT_VERSION)
        self.assertEqual(result["generation_metadata"]["model_id"], "test-chat-model")
        self.assertEqual(result["generation_metadata"]["temperature"], 0.0)
        self.assertEqual(result["generation_metadata"]["finish_reason"], "stop")
        self.assertEqual(result["generation_metadata"]["token_usage"]["total_tokens"], 155)
        self.assertGreaterEqual(result["generation_metadata"]["latency_ms"], 0)
        self.assertIsNotNone(model.messages)

    def test_invoke_accepts_insufficient_evidence_payload(self) -> None:
        generator, _ = self.make_generator(
            answered_payload(
                candidate_response_type="insufficient_evidence",
                draft_message="현재 자료만으로는 답하기 어렵습니다.",
                used_chunk_ids=[],
            )
        )

        result = generator.invoke(make_request())

        self.assertEqual(result["candidate_response_type"], "insufficient_evidence")
        self.assertEqual(result["used_chunk_ids"], [])

    def test_invoke_accepts_clarification_options_with_known_ids(self) -> None:
        generator, _ = self.make_generator(
            answered_payload(
                candidate_response_type="needs_clarification",
                draft_message="어떤 길쌈노래를 말씀하셨나요?",
                used_chunk_ids=[],
                clarification={
                    "reason_code": "ambiguous_scope",
                    "question": "어떤 길쌈노래를 말씀하셨나요?",
                    "options": [
                        {"id": "option-1", "label": "길쌈노래", "source_chunk_ids": [CHUNK_ID]}
                    ],
                },
            )
        )

        result = generator.invoke(make_request())

        self.assertEqual(result["candidate_response_type"], "needs_clarification")

    def test_invoke_accepts_premise_correction_with_known_ids(self) -> None:
        generator, _ = self.make_generator(
            answered_payload(
                candidate_response_type="corrected_premise",
                premise_correction={
                    "original_premise": "길쌈노래는 궁중음악이다.",
                    "corrected_premise": "길쌈노래는 길쌈을 하며 부르던 민요이다.",
                    "source_chunk_ids": [CHUNK_ID],
                },
            )
        )

        result = generator.invoke(make_request())

        self.assertEqual(result["premise_correction"]["source_chunk_ids"], [CHUNK_ID])

    def test_invoke_rejects_non_json_model_response(self) -> None:
        generator, _ = self.make_generator("답변입니다.", raw=True)

        with self.assertRaisesRegex(RagServiceError, "one JSON object"):
            generator.invoke(make_request())

    def test_invoke_rejects_missing_model_output_field(self) -> None:
        payload = answered_payload()
        del payload["clarification"]
        generator, _ = self.make_generator(payload)

        with self.assertRaisesRegex(RagServiceError, "fields do not match"):
            generator.invoke(make_request())

    def test_invoke_rejects_unknown_chunk_id(self) -> None:
        generator, _ = self.make_generator(answered_payload(used_chunk_ids=["unknown-chunk-id"]))

        with self.assertRaisesRegex(RagServiceError, "unknown chunk_id"):
            generator.invoke(make_request())

    def test_generator_connects_to_rag_service_without_an_api_call(self) -> None:
        generator, _ = self.make_generator(answered_payload())
        service = RagService(
            retriever=FakeRetriever(),
            generator=generator,
            evidence_checker=FakeEvidenceChecker(),
        )

        response = service.answer("길쌈노래를 쉽게 설명해줘", audience_level="easy")

        self.assertEqual(response["response_type"], "answered")
        self.assertEqual(response["message"], answered_payload()["draft_message"])
        self.assertEqual(response["citations"][0]["chunk_id"], CHUNK_ID)
        self.assertEqual(response["citations"][0]["content"], CONTEXT["content"])


if __name__ == "__main__":
    unittest.main()
