from __future__ import annotations

import json
import time
from typing import Any, Protocol

from rag_service.errors import RagServiceError

from .prompt_baseline import PROMPT_VERSION, build_messages


MODEL_OUTPUT_FIELDS = {
    "candidate_response_type",
    "draft_message",
    "used_chunk_ids",
    "clarification",
    "premise_correction",
    "related_topic_candidates",
}
RESPONSE_TYPES = {
    "answered",
    "insufficient_evidence",
    "needs_clarification",
    "corrected_premise",
    "safety_refusal",
    "out_of_scope",
}
REQUIRED_REQUEST_FIELDS = {
    "schema_version",
    "request_id",
    "interaction_id",
    "question",
    "audience_level",
    "response_language",
    "retrieved_contexts",
    "grounding_decision",
}


class ChatModel(Protocol):
    """Minimal interface shared by LangChain chat models and test doubles."""

    def invoke(self, messages: list[dict[str, str]]) -> Any: ...


class PromptBaselineGenerator:
    """Run prompt-baseline-v0 and assemble the GenerationResult envelope."""

    def __init__(
        self,
        model: ChatModel,
        *,
        model_id: str,
        temperature: float | None = None,
        prompt_version: str = PROMPT_VERSION,
    ) -> None:
        if not model_id.strip():
            raise ValueError("model_id must not be empty")
        self.model = model
        self.model_id = model_id
        self.temperature = temperature
        self.prompt_version = prompt_version

    def invoke(self, request: dict[str, Any]) -> dict[str, Any]:
        self._validate_request(request)
        messages = build_messages(request)

        started_at = time.perf_counter()
        response = self.model.invoke(messages)
        latency_ms = round((time.perf_counter() - started_at) * 1000, 3)

        payload = self._parse_payload(response)
        self._validate_payload(payload, request["retrieved_contexts"])

        return {
            "schema_version": request["schema_version"],
            "request_id": request["request_id"],
            "interaction_id": request["interaction_id"],
            "candidate_response_type": payload["candidate_response_type"],
            "draft_message": payload["draft_message"],
            "audience_level": request["audience_level"],
            "used_chunk_ids": payload["used_chunk_ids"],
            "clarification": payload["clarification"],
            "premise_correction": payload["premise_correction"],
            "related_topic_candidates": payload["related_topic_candidates"],
            "generation_metadata": {
                "prompt_version": self.prompt_version,
                "model_id": self.model_id,
                "temperature": self.temperature,
                "finish_reason": self._finish_reason(response),
                "latency_ms": latency_ms,
                "token_usage": self._token_usage(response),
            },
        }

    @staticmethod
    def _validate_request(request: Any) -> None:
        if not isinstance(request, dict) or not REQUIRED_REQUEST_FIELDS.issubset(request):
            raise RagServiceError("generation_error", "generation request fields are incomplete")
        if not isinstance(request["retrieved_contexts"], list):
            raise RagServiceError("generation_error", "retrieved_contexts must be a list")

    @staticmethod
    def _parse_payload(response: Any) -> dict[str, Any]:
        content = response if isinstance(response, str) else getattr(response, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise RagServiceError("generation_error", "model response content must be a non-empty string")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RagServiceError("generation_error", "model response must be one JSON object") from exc
        if not isinstance(payload, dict):
            raise RagServiceError("generation_error", "model response JSON must be an object")
        return payload

    @classmethod
    def _validate_payload(cls, payload: dict[str, Any], contexts: list[dict[str, Any]]) -> None:
        if set(payload) != MODEL_OUTPUT_FIELDS:
            raise RagServiceError("generation_error", "model output fields do not match the prompt contract")
        if payload["candidate_response_type"] not in RESPONSE_TYPES:
            raise RagServiceError("generation_error", "model returned an unsupported response type")
        if not isinstance(payload["draft_message"], str) or not payload["draft_message"].strip():
            raise RagServiceError("generation_error", "draft_message must be a non-empty string")
        if not cls._is_string_list(payload["used_chunk_ids"]):
            raise RagServiceError("generation_error", "used_chunk_ids must be a list of non-empty strings")
        if payload["clarification"] is not None and not isinstance(payload["clarification"], dict):
            raise RagServiceError("generation_error", "clarification must be an object or null")
        if payload["premise_correction"] is not None and not isinstance(payload["premise_correction"], dict):
            raise RagServiceError("generation_error", "premise_correction must be an object or null")
        if not isinstance(payload["related_topic_candidates"], list):
            raise RagServiceError("generation_error", "related_topic_candidates must be a list")

        allowed_ids = {
            context.get("chunk_id")
            for context in contexts
            if isinstance(context, dict) and isinstance(context.get("chunk_id"), str)
        }
        referenced_ids = set(payload["used_chunk_ids"])
        referenced_ids.update(cls._source_chunk_ids(payload))
        if not referenced_ids.issubset(allowed_ids):
            raise RagServiceError("generation_error", "model output refers to an unknown chunk_id")

    @classmethod
    def _source_chunk_ids(cls, value: Any) -> list[str]:
        found: list[str] = []
        if isinstance(value, dict):
            for key, nested in value.items():
                if key == "source_chunk_ids":
                    if not cls._is_string_list(nested):
                        raise RagServiceError(
                            "generation_error",
                            "source_chunk_ids must be a list of non-empty strings",
                        )
                    found.extend(nested)
                else:
                    found.extend(cls._source_chunk_ids(nested))
        elif isinstance(value, list):
            for nested in value:
                found.extend(cls._source_chunk_ids(nested))
        return found

    @staticmethod
    def _is_string_list(value: Any) -> bool:
        return isinstance(value, list) and all(isinstance(item, str) and item for item in value)

    @staticmethod
    def _finish_reason(response: Any) -> str | None:
        metadata = getattr(response, "response_metadata", None)
        if not isinstance(metadata, dict):
            return None
        value = metadata.get("finish_reason")
        return value if isinstance(value, str) else None

    @staticmethod
    def _token_usage(response: Any) -> dict[str, Any] | None:
        usage = getattr(response, "usage_metadata", None)
        if isinstance(usage, dict):
            return usage
        metadata = getattr(response, "response_metadata", None)
        if isinstance(metadata, dict) and isinstance(metadata.get("token_usage"), dict):
            return metadata["token_usage"]
        return None
