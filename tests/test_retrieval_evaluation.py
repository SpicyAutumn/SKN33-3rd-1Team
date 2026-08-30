from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from evaluate_aks_retrieval import score_case  # noqa: E402


def test_score_case_accepts_any_chunk_from_the_expected_document() -> None:
    case = {
        "case_id": "case-1",
        "question": "질문",
        "expected_document_id": "aks:E0000003",
        "expected_title": "ㄱ당",
        "category": "역사",
    }
    results = [
        {"retrieval_rank": 1, "document_id": "aks:E0000002", "title": "ㄱ", "section": "definition", "retrieval_score": 0.7},
        {"retrieval_rank": 2, "document_id": "aks:E0000003", "title": "ㄱ당", "section": "body", "retrieval_score": 0.6},
    ]

    result = score_case(case, results)

    assert result["hit_rank"] == 2
    assert result["reciprocal_rank"] == 0.5
