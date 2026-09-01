from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from evaluation import load_evaluation_cases, summarize_cases


class EvaluationCaseLoaderTest(unittest.TestCase):
    def test_loads_and_summarizes_case_file(self) -> None:
        contents = (
            '{"case_id":"DEV-001","split":"dev","question":"질문",'
            '"expected_response_type":"answered","expected_document_ids":["aks:E1"],'
            '"rationale":"근거 있음","review_status":"approved"}\n'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.jsonl"
            path.write_text(contents, encoding="utf-8")
            cases = load_evaluation_cases(path, expected_split="dev")

        summary = summarize_cases(cases)
        self.assertEqual(summary["case_count"], 1)
        self.assertEqual(summary["response_type_counts"], {"answered": 1})

    def test_rejects_duplicate_case_id(self) -> None:
        line = (
            '{"case_id":"DEV-001","split":"dev","question":"질문",'
            '"expected_response_type":"out_of_scope","expected_document_ids":[],'
            '"rationale":"범위 밖","review_status":"draft"}\n'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.jsonl"
            path.write_text(line + line, encoding="utf-8")
            with self.assertRaises(ValueError):
                load_evaluation_cases(path, expected_split="dev")

    def test_answer_case_requires_expected_document(self) -> None:
        contents = (
            '{"case_id":"DEV-001","split":"dev","question":"질문",'
            '"expected_response_type":"answered","expected_document_ids":[],'
            '"rationale":"잘못된 라벨","review_status":"draft"}\n'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.jsonl"
            path.write_text(contents, encoding="utf-8")
            with self.assertRaises(ValueError):
                load_evaluation_cases(path, expected_split="dev")

    def test_accepts_a_separate_regression_split(self) -> None:
        contents = (
            '{"case_id":"REG-001","split":"regression","question":"문화재 질문",'
            '"expected_response_type":"answered","expected_document_ids":["aks:E1"],'
            '"rationale":"고유명사 회귀 확인","review_status":"draft"}\n'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.jsonl"
            path.write_text(contents, encoding="utf-8")
            cases = load_evaluation_cases(path, expected_split="regression")

        self.assertEqual(cases[0]["case_id"], "REG-001")


if __name__ == "__main__":
    unittest.main()
