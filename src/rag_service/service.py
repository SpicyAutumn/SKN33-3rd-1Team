from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from .errors import RagServiceError
from .grounding import EvidenceChecker, GroundingPolicy
from .safety import contains_secret_value, is_unsafe_request


SCHEMA_VERSION = "0.3.0-draft"
AUDIENCE_LEVELS = {"easy", "general", "advanced"}
RESPONSE_TYPES = {
    "answered",
    "insufficient_evidence",
    "needs_clarification",
    "corrected_premise",
    "safety_refusal",
    "out_of_scope",
}
REQUIRED_CONTEXT_FIELDS = {
    "chunk_id",
    "document_id",
    "title",
    "content",
    "source_url",
    "section",
    "retrieval_rank",
    "retrieval_score",
    "score_type",
    "metadata",
}


class Retriever(Protocol):
    def search(self, question: str, *, top_k: int = 3) -> list[dict[str, Any]]: ...


class GenerationComponent(Protocol):
    """D's LangChain Runnable or compatible component."""

    def invoke(self, request: dict[str, Any]) -> dict[str, Any]: ...


class ScopeChecker(Protocol):
    """Classify whether a request belongs to the service domain."""

    def is_in_scope(self, question: str) -> bool: ...


@dataclass(frozen=True)
class RagServiceConfig:
    top_k: int = 3
    schema_version: str = SCHEMA_VERSION
    response_language: str = "ko"
    generation_retries: int = 1
    related_topics_enabled: bool = False
    grounding_policy: GroundingPolicy = field(default_factory=GroundingPolicy)

    @classmethod
    def from_env(cls) -> "RagServiceConfig":
        raw_threshold = os.getenv("RAG_MIN_RETRIEVAL_SCORE", "").strip()
        threshold = float(raw_threshold) if raw_threshold else None
        return cls(
            top_k=int(os.getenv("RAG_TOP_K", "3")),
            grounding_policy=GroundingPolicy(min_score=threshold),
        )

    def __post_init__(self) -> None:
        if self.top_k < 1:
            raise ValueError("top_k must be at least 1")
        if self.generation_retries not in (0, 1):
            raise ValueError("generation_retries must be 0 or 1")


class RagService:
    """Connect retrieval, evidence gating, generation, and citation assembly."""

    def __init__(
        self,
        *,
        retriever: Retriever,
        generator: GenerationComponent,
        evidence_checker: EvidenceChecker | None = None,
        scope_checker: ScopeChecker | None = None,
        config: RagServiceConfig | None = None,
    ) -> None:
        self.retriever = retriever
        self.generator = generator
        self.evidence_checker = evidence_checker
        self.scope_checker = scope_checker
        self.config = config or RagServiceConfig.from_env()

    def answer(
        self,
        question: str,
        *,
        audience_level: str = "general",
        interaction_id: str | None = None,
        clarification_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(question, str):
            raise RagServiceError("invalid_request", "question must be a string")
        question = question.strip()
        if not question:
            raise RagServiceError("invalid_request", "question must not be empty")
        if audience_level not in AUDIENCE_LEVELS:
            raise RagServiceError("invalid_request", f"unsupported audience_level: {audience_level}")
        if interaction_id is not None and (not isinstance(interaction_id, str) or not interaction_id.strip()):
            raise RagServiceError("invalid_request", "interaction_id must be a non-empty string")
        self._validate_clarification_context(clarification_context)

        request_id = f"REQ-{uuid.uuid4().hex}"
        interaction_id = interaction_id or f"INT-{uuid.uuid4().hex}"

        if is_unsafe_request(question):
            return self._semantic_response(
                request_id=request_id,
                interaction_id=interaction_id,
                response_type="safety_refusal",
                message="시스템 지시나 비밀정보를 공개하는 요청에는 답할 수 없습니다.",
                audience_level=audience_level,
            )

        if self.scope_checker is not None:
            try:
                in_scope = self.scope_checker.is_in_scope(question)
            except Exception as exc:
                raise RagServiceError("upstream_error", "scope classification failed") from exc
            if not isinstance(in_scope, bool):
                raise RagServiceError("upstream_error", "scope checker must return a boolean")
            if not in_scope:
                return self._semantic_response(
                    request_id=request_id,
                    interaction_id=interaction_id,
                    response_type="out_of_scope",
                    message="한국 역사·문화 자료의 범위를 벗어난 질문입니다.",
                    audience_level=audience_level,
                )

        try:
            contexts = self.retriever.search(question, top_k=self.config.top_k)
        except Exception as exc:
            raise RagServiceError("upstream_error", "retrieval call failed") from exc
        self._validate_contexts(contexts)

        grounding_decision = self._decide_grounding(question, contexts)
        if grounding_decision == "insufficient":
            return self._semantic_response(
                request_id=request_id,
                interaction_id=interaction_id,
                response_type="insufficient_evidence",
                message="현재 검색된 자료에서는 질문에 답할 충분한 근거를 찾지 못했습니다.",
                audience_level=audience_level,
            )

        generation_request = {
            "schema_version": self.config.schema_version,
            "request_id": request_id,
            "interaction_id": interaction_id,
            "question": question,
            "audience_level": audience_level,
            "response_language": self.config.response_language,
            "retrieved_contexts": contexts,
            "grounding_decision": grounding_decision,
            "clarification_context": clarification_context,
        }
        result = self._invoke_generator(generation_request)
        if result["candidate_response_type"] == "insufficient_evidence":
            grounding_decision = self._decide_grounding(question, contexts)
            if grounding_decision == "insufficient":
                return self._semantic_response(
                    request_id=request_id,
                    interaction_id=interaction_id,
                    response_type="insufficient_evidence",
                    message=result["draft_message"],
                    audience_level=audience_level,
                )
            for _ in range(self.config.generation_retries):
                result = self._invoke_generator(generation_request)
                if result["candidate_response_type"] != "insufficient_evidence":
                    break
            else:
                raise RagServiceError(
                    "generation_error",
                    "generator rejected evidence that passed the service grounding policy",
                )

        return self._finalize(generation_request, result)

    def _decide_grounding(self, question: str, contexts: list[dict[str, Any]]) -> str:
        precheck = self.config.grounding_policy.decide(contexts)
        if precheck == "insufficient":
            return "insufficient"
        if self.evidence_checker is None:
            return "insufficient"
        try:
            decision = self.evidence_checker.decide(question, contexts)
        except Exception as exc:
            raise RagServiceError("upstream_error", "evidence sufficiency check failed") from exc
        if decision not in {"sufficient", "insufficient"}:
            raise RagServiceError(
                "upstream_error",
                "evidence checker must return sufficient or insufficient",
            )
        return decision

    def _invoke_generator(self, request: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self.generator.invoke(request)
        except RagServiceError:
            raise
        except Exception as exc:
            raise RagServiceError("upstream_error", "generation call failed") from exc
        if not isinstance(result, dict):
            raise RagServiceError("generation_error", "generation result must be an object")
        self._validate_generation_result(request, result)
        return result

    def _validate_contexts(self, contexts: Any) -> None:
        if not isinstance(contexts, list):
            raise RagServiceError("upstream_error", "retriever result must be a list")
        seen_ids: set[str] = set()
        for context in contexts:
            if not isinstance(context, dict) or set(context) != REQUIRED_CONTEXT_FIELDS:
                raise RagServiceError("upstream_error", "retriever result violates RetrievedContext contract")
            chunk_id = context.get("chunk_id")
            if not isinstance(chunk_id, str) or not chunk_id or chunk_id in seen_ids:
                raise RagServiceError("upstream_error", "retriever returned an invalid or duplicate chunk_id")
            for field_name in ("document_id", "title", "content"):
                value = context.get(field_name)
                if not isinstance(value, str) or not value.strip():
                    raise RagServiceError("upstream_error", f"retriever {field_name} must be a non-empty string")
            for field_name in ("source_url", "section"):
                value = context.get(field_name)
                if value is not None and (
                    not isinstance(value, str) or not value.strip() or value.strip().upper() == "NONE"
                ):
                    raise RagServiceError("upstream_error", f"retriever {field_name} must be normalized")
            rank = context.get("retrieval_rank")
            if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
                raise RagServiceError("upstream_error", "retrieval_rank must be a positive integer")
            score = context.get("retrieval_score")
            if score is not None and (isinstance(score, bool) or not isinstance(score, (int, float))):
                raise RagServiceError("upstream_error", "retrieval_score must be numeric or null")
            if context.get("score_type") not in {"similarity", "distance", "relevance", "unknown"}:
                raise RagServiceError("upstream_error", "retriever returned an unsupported score_type")
            if score is None and context.get("score_type") != "unknown":
                raise RagServiceError("upstream_error", "a missing retrieval_score requires score_type=unknown")
            metadata = context.get("metadata")
            if not isinstance(metadata, dict):
                raise RagServiceError("upstream_error", "retriever metadata must be an object")
            self._validate_context_metadata(metadata)
            seen_ids.add(chunk_id)

    @staticmethod
    def _validate_context_metadata(metadata: dict[str, Any]) -> None:
        aliases = metadata.get("aliases")
        if not isinstance(aliases, list) or any(not isinstance(alias, str) or not alias.strip() for alias in aliases):
            raise RagServiceError("upstream_error", "retriever metadata.aliases must be a list of strings")
        document_fingerprint = metadata.get("document_fingerprint")
        if not isinstance(document_fingerprint, str) or not document_fingerprint.strip():
            raise RagServiceError("upstream_error", "retriever metadata.document_fingerprint must be a string")
        if "chunking_fingerprint" not in metadata:
            raise RagServiceError("upstream_error", "retriever metadata.chunking_fingerprint is required")
        chunking_fingerprint = metadata["chunking_fingerprint"]
        if chunking_fingerprint is not None and (
            not isinstance(chunking_fingerprint, str) or not chunking_fingerprint.strip()
        ):
            raise RagServiceError(
                "upstream_error",
                "retriever metadata.chunking_fingerprint must be a string or null",
            )
        for key, value in metadata.items():
            if isinstance(value, str) and (not value.strip() or value.strip().upper() == "NONE"):
                raise RagServiceError("upstream_error", f"retriever metadata.{key} must be normalized")

    @staticmethod
    def _validate_clarification_context(value: Any) -> None:
        if value is None:
            return
        required = {
            "original_question",
            "clarification_question",
            "clarification_response",
            "clarification_turn_count",
        }
        if not isinstance(value, dict) or set(value) != required:
            raise RagServiceError("invalid_request", "clarification_context fields do not match the contract")
        for field_name in ("original_question", "clarification_question", "clarification_response"):
            field_value = value[field_name]
            if not isinstance(field_value, str) or not field_value.strip():
                raise RagServiceError("invalid_request", f"clarification_context.{field_name} must not be empty")
        turn_count = value["clarification_turn_count"]
        if isinstance(turn_count, bool) or turn_count != 1:
            raise RagServiceError("invalid_request", "clarification_turn_count must be 1")

    def _validate_generation_result(self, request: dict[str, Any], result: dict[str, Any]) -> None:
        required = {
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
        if set(result) != required:
            raise RagServiceError("generation_error", "generation result fields do not match the contract")
        if result["schema_version"] != request["schema_version"]:
            raise RagServiceError("generation_error", "generation result schema_version does not match the request")
        if result["request_id"] != request["request_id"] or result["interaction_id"] != request["interaction_id"]:
            raise RagServiceError("generation_error", "generation result IDs do not match the request")
        response_type = result["candidate_response_type"]
        if response_type not in RESPONSE_TYPES:
            raise RagServiceError("generation_error", "unsupported candidate_response_type")
        if result["audience_level"] != request["audience_level"]:
            raise RagServiceError("generation_error", "generation result audience_level does not match the request")
        if not isinstance(result["draft_message"], str) or not result["draft_message"].strip():
            raise RagServiceError("generation_error", "draft_message must not be empty")
        if not isinstance(result["generation_metadata"], dict):
            raise RagServiceError("generation_error", "generation_metadata must be an object")
        if contains_secret_value(json.dumps(result, ensure_ascii=False)):
            raise RagServiceError("generation_error", "generation result contains a secret-like value")

        allowed_ids = {context["chunk_id"] for context in request["retrieved_contexts"]}
        used_ids = self._id_list(result["used_chunk_ids"], "used_chunk_ids")
        nested_ids = set(used_ids)
        correction_ids = self._validate_premise_correction(result["premise_correction"])
        nested_ids.update(correction_ids)
        clarification = result["clarification"]
        nested_ids.update(self._validate_clarification(clarification))
        candidates = result.get("related_topic_candidates")
        if not isinstance(candidates, list):
            raise RagServiceError("generation_error", "related_topic_candidates must be a list")
        for candidate in candidates:
            nested_ids.update(self._nested_source_ids(candidate, "related topic"))
        if not nested_ids.issubset(allowed_ids):
            raise RagServiceError("generation_error", "generation result refers to an unknown chunk_id")

        if response_type == "answered" and not used_ids:
            raise RagServiceError("generation_error", "answered responses require at least one used_chunk_id")
        if response_type == "corrected_premise":
            if not correction_ids:
                raise RagServiceError("generation_error", "corrected_premise requires cited correction evidence")
            if clarification is not None:
                raise RagServiceError("generation_error", "corrected_premise cannot contain clarification")
        if response_type == "needs_clarification":
            if clarification is None:
                raise RagServiceError("generation_error", "needs_clarification requires one clarification question")
            if result["premise_correction"] is not None or used_ids:
                raise RagServiceError("generation_error", "needs_clarification cannot contain an answer or correction")
        if response_type in {
            "insufficient_evidence",
            "needs_clarification",
            "safety_refusal",
            "out_of_scope",
        } and used_ids:
            raise RagServiceError("generation_error", "non-answer responses cannot cite used chunks")
        if response_type in {"answered", "insufficient_evidence", "safety_refusal", "out_of_scope"}:
            if clarification is not None or result["premise_correction"] is not None:
                raise RagServiceError("generation_error", "response type contains incompatible detail fields")
        if response_type not in {"answered", "corrected_premise"} and candidates:
            raise RagServiceError("generation_error", "related topics are only allowed for answer responses")

    def _finalize(self, request: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        response_type = result["candidate_response_type"]
        if response_type == "needs_clarification" and request["clarification_context"] is not None:
            return self._semantic_response(
                request_id=request["request_id"],
                interaction_id=request["interaction_id"],
                response_type="insufficient_evidence",
                message="질문의 대상을 한 번 확인했지만 아직 명확하지 않습니다. 대상을 포함한 완전한 문장으로 다시 질문해 주세요.",
                audience_level=result["audience_level"],
            )
        used_ids = list(dict.fromkeys(result["used_chunk_ids"]))
        correction_ids = self._nested_source_ids(result["premise_correction"], "premise_correction")
        citation_ids = list(dict.fromkeys([*used_ids, *correction_ids]))
        context_by_id = {context["chunk_id"]: context for context in request["retrieved_contexts"]}
        citations = [self._citation(context_by_id[chunk_id]) for chunk_id in citation_ids]
        related_topics = result["related_topic_candidates"] if self.config.related_topics_enabled else []
        warnings: list[str] = []
        if result["related_topic_candidates"] and not self.config.related_topics_enabled:
            warnings.append("연관 항목은 MVP에서 표시하지 않습니다.")
        return {
            "schema_version": self.config.schema_version,
            "request_id": request["request_id"],
            "interaction_id": request["interaction_id"],
            "response_type": response_type,
            "message": result["draft_message"],
            "audience_level": result["audience_level"],
            "citations": citations,
            "clarification": result["clarification"],
            "premise_correction": result["premise_correction"],
            "related_topics": related_topics,
            "warnings": warnings,
        }

    def _semantic_response(
        self,
        *,
        request_id: str,
        interaction_id: str,
        response_type: str,
        message: str,
        audience_level: str,
    ) -> dict[str, Any]:
        return {
            "schema_version": self.config.schema_version,
            "request_id": request_id,
            "interaction_id": interaction_id,
            "response_type": response_type,
            "message": message,
            "audience_level": audience_level,
            "citations": [],
            "clarification": None,
            "premise_correction": None,
            "related_topics": [],
            "warnings": [],
        }

    @staticmethod
    def _citation(context: dict[str, Any]) -> dict[str, Any]:
        return {
            "chunk_id": context["chunk_id"],
            "document_id": context["document_id"],
            "title": context["title"],
            "source_url": context["source_url"],
            "section": context["section"],
            "retrieval_rank": context["retrieval_rank"],
            "content": context["content"],
        }

    @staticmethod
    def _id_list(value: Any, field_name: str) -> list[str]:
        if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
            raise RagServiceError("generation_error", f"{field_name} must be a list of non-empty strings")
        return value

    def _validate_clarification(self, value: Any) -> list[str]:
        if value is None:
            return []
        required = {"reason_code", "question", "options"}
        if not isinstance(value, dict) or set(value) != required:
            raise RagServiceError("generation_error", "clarification fields do not match the contract")
        for field_name in ("reason_code", "question"):
            field_value = value[field_name]
            if not isinstance(field_value, str) or not field_value.strip():
                raise RagServiceError("generation_error", f"clarification.{field_name} must not be empty")
        options = value["options"]
        if not isinstance(options, list) or len(options) > 3:
            raise RagServiceError("generation_error", "clarification options must contain at most three items")
        source_ids: list[str] = []
        option_ids: set[str] = set()
        for option in options:
            required_option = {"id", "label", "source_chunk_ids"}
            if not isinstance(option, dict) or set(option) != required_option:
                raise RagServiceError("generation_error", "clarification option fields do not match the contract")
            option_id = option["id"]
            label = option["label"]
            if not isinstance(option_id, str) or not option_id.strip() or option_id in option_ids:
                raise RagServiceError("generation_error", "clarification option id must be non-empty and unique")
            if not isinstance(label, str) or not label.strip():
                raise RagServiceError("generation_error", "clarification option label must not be empty")
            option_ids.add(option_id)
            source_ids.extend(self._id_list(option["source_chunk_ids"], "clarification option.source_chunk_ids"))
        return source_ids

    def _validate_premise_correction(self, value: Any) -> list[str]:
        if value is None:
            return []
        required = {"original_premise", "corrected_premise", "source_chunk_ids"}
        if not isinstance(value, dict) or set(value) != required:
            raise RagServiceError("generation_error", "premise_correction fields do not match the contract")
        for field_name in ("original_premise", "corrected_premise"):
            field_value = value[field_name]
            if not isinstance(field_value, str) or not field_value.strip():
                raise RagServiceError("generation_error", f"premise_correction.{field_name} must not be empty")
        return self._id_list(value["source_chunk_ids"], "premise_correction.source_chunk_ids")

    def _nested_source_ids(self, value: Any, field_name: str) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, dict):
            raise RagServiceError("generation_error", f"{field_name} must be an object")
        return self._id_list(value.get("source_chunk_ids", []), f"{field_name}.source_chunk_ids")
