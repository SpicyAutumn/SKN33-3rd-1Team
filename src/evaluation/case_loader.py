from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .service_metrics import RESPONSE_TYPES


SPLITS = {"dev", "holdout"}
REVIEW_STATUSES = {"draft", "approved"}


def load_evaluation_cases(path: Path, *, expected_split: str | None = None) -> list[dict[str, Any]]:
    """Load and validate the human-labelled RAG evaluation JSONL."""

    if expected_split is not None and expected_split not in SPLITS:
        raise ValueError(f"unsupported expected_split: {expected_split}")
    cases: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            case = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number} contains invalid JSON") from exc
        _validate_case(case, path=path, line_number=line_number, expected_split=expected_split)
        if case["case_id"] in seen_ids:
            raise ValueError(f"{path}:{line_number} duplicates case_id {case['case_id']}")
        seen_ids.add(case["case_id"])
        cases.append(case)
    if not cases:
        raise ValueError(f"no evaluation cases found in {path}")
    return cases


def summarize_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    if not cases:
        raise ValueError("at least one evaluation case is required")
    return {
        "case_count": len(cases),
        "response_type_counts": dict(sorted(Counter(case["expected_response_type"] for case in cases).items())),
        "review_status_counts": dict(sorted(Counter(case["review_status"] for case in cases).items())),
    }


def _validate_case(
    case: Any,
    *,
    path: Path,
    line_number: int,
    expected_split: str | None,
) -> None:
    required = {
        "case_id",
        "split",
        "question",
        "expected_response_type",
        "expected_document_ids",
        "rationale",
        "review_status",
    }
    if not isinstance(case, dict) or not required.issubset(case):
        raise ValueError(f"{path}:{line_number} fields do not match the evaluation case contract")
    for field_name in ("case_id", "question", "rationale"):
        if not isinstance(case[field_name], str) or not case[field_name].strip():
            raise ValueError(f"{path}:{line_number} {field_name} must be a non-empty string")
    split = case["split"]
    if split not in SPLITS or (expected_split is not None and split != expected_split):
        raise ValueError(f"{path}:{line_number} has an invalid split")
    response_type = case["expected_response_type"]
    if response_type not in RESPONSE_TYPES:
        raise ValueError(f"{path}:{line_number} has an invalid expected_response_type")
    document_ids = case["expected_document_ids"]
    if not isinstance(document_ids, list) or any(
        not isinstance(document_id, str) or not document_id.strip() for document_id in document_ids
    ):
        raise ValueError(f"{path}:{line_number} expected_document_ids must be a string list")
    if response_type in {"answered", "corrected_premise"} and not document_ids:
        raise ValueError(f"{path}:{line_number} answer cases require expected_document_ids")
    if response_type in {"needs_clarification", "safety_refusal", "out_of_scope"} and document_ids:
        raise ValueError(f"{path}:{line_number} this response type cannot require citations")
    if case["review_status"] not in REVIEW_STATUSES:
        raise ValueError(f"{path}:{line_number} has an invalid review_status")
