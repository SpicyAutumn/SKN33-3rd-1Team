from __future__ import annotations

from statistics import mean
from typing import Any, Iterable


ABSTENTION_TYPES = {
    "insufficient_evidence",
    "needs_clarification",
    "safety_refusal",
    "out_of_scope",
}
RESPONSE_TYPES = ABSTENTION_TYPES | {"answered", "corrected_premise"}


def score_response(case: dict[str, Any], response: dict[str, Any], *, latency_ms: float) -> dict[str, Any]:
    """Score contract-stable fields of one service response.

    Faithfulness and answer relevancy are intentionally excluded because those
    need a separately selected judge or human rubric.
    """

    case_id = _non_empty_text(case.get("case_id"), "case.case_id")
    expected_type = _response_type(case.get("expected_response_type"), "case.expected_response_type")
    actual_type = _response_type(response.get("response_type"), "response.response_type")
    if isinstance(latency_ms, bool) or not isinstance(latency_ms, (int, float)) or latency_ms < 0:
        raise ValueError("latency_ms must be a non-negative number")

    expected_ids = _string_set(case.get("expected_document_ids", []), "case.expected_document_ids")
    citations = response.get("citations")
    if not isinstance(citations, list):
        raise ValueError("response.citations must be a list")
    cited_ids: list[str] = []
    for citation in citations:
        if not isinstance(citation, dict):
            raise ValueError("each citation must be an object")
        cited_ids.append(_non_empty_text(citation.get("document_id"), "citation.document_id"))

    unique_cited_ids = set(cited_ids)
    correct_cited_ids = unique_cited_ids & expected_ids
    citation_precision = len(correct_cited_ids) / len(unique_cited_ids) if unique_cited_ids else None
    citation_recall = len(correct_cited_ids) / len(expected_ids) if expected_ids else None
    expected_abstention = expected_type in ABSTENTION_TYPES
    actual_abstention = actual_type in ABSTENTION_TYPES

    return {
        "case_id": case_id,
        "expected_response_type": expected_type,
        "actual_response_type": actual_type,
        "response_type_correct": actual_type == expected_type,
        "expected_abstention": expected_abstention,
        "actual_abstention": actual_abstention,
        "abstention_correct": expected_abstention == actual_abstention,
        "expected_document_ids": sorted(expected_ids),
        "cited_document_ids": sorted(unique_cited_ids),
        "correct_cited_document_ids": sorted(correct_cited_ids),
        "citation_precision": citation_precision,
        "citation_recall": citation_recall,
        "latency_ms": float(latency_ms),
    }


def aggregate_results(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(results)
    if not rows:
        raise ValueError("at least one evaluation result is required")
    for row in rows:
        required = {
            "response_type_correct",
            "abstention_correct",
            "citation_precision",
            "citation_recall",
            "latency_ms",
        }
        if not isinstance(row, dict) or not required.issubset(row):
            raise ValueError("evaluation result fields do not match the metric contract")

    precision_values = [row["citation_precision"] for row in rows if row["citation_precision"] is not None]
    recall_values = [row["citation_recall"] for row in rows if row["citation_recall"] is not None]
    return {
        "case_count": len(rows),
        "response_type_accuracy": mean(bool(row["response_type_correct"]) for row in rows),
        "abstention_accuracy": mean(bool(row["abstention_correct"]) for row in rows),
        "mean_citation_precision": mean(precision_values) if precision_values else None,
        "mean_citation_recall": mean(recall_values) if recall_values else None,
        "mean_latency_ms": mean(float(row["latency_ms"]) for row in rows),
    }


def _response_type(value: Any, field_name: str) -> str:
    value = _non_empty_text(value, field_name)
    if value not in RESPONSE_TYPES:
        raise ValueError(f"{field_name} is unsupported")
    return value


def _non_empty_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _string_set(value: Any, field_name: str) -> set[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    result: set[str] = set()
    for item in value:
        result.add(_non_empty_text(item, field_name))
    return result
