from __future__ import annotations

import unittest
from pathlib import Path

from evaluation import load_evaluation_cases
from rag_service.safety import is_unsafe_request


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SafetyEvaluationCasesTest(unittest.TestCase):
    def test_all_safety_cases_are_caught_by_precheck(self) -> None:
        paths = (
            ("dev", PROJECT_ROOT / "data" / "evaluation" / "aks_rag_dev_v1.jsonl"),
            ("holdout", PROJECT_ROOT / "data" / "evaluation" / "aks_rag_holdout_v1.jsonl"),
        )
        missed: list[str] = []
        for split, path in paths:
            cases = load_evaluation_cases(path, expected_split=split)
            missed.extend(
                case["case_id"]
                for case in cases
                if case["expected_response_type"] == "safety_refusal" and not is_unsafe_request(case["question"])
            )

        self.assertEqual(missed, [])


if __name__ == "__main__":
    unittest.main()
