from __future__ import annotations

import unittest

from evaluation import aggregate_results, score_response


class ServiceEvaluationTest(unittest.TestCase):
    def test_scores_response_type_citation_and_latency(self) -> None:
        case = {
            "case_id": "RAG-DEV-001",
            "expected_response_type": "answered",
            "expected_document_ids": ["aks:E0000003"],
        }
        response = {
            "response_type": "answered",
            "citations": [
                {"document_id": "aks:E0000003"},
                {"document_id": "aks:E9999999"},
            ],
        }

        result = score_response(case, response, latency_ms=125.5)

        self.assertTrue(result["response_type_correct"])
        self.assertEqual(result["citation_precision"], 0.5)
        self.assertEqual(result["citation_recall"], 1.0)
        self.assertEqual(result["latency_ms"], 125.5)

    def test_scores_correct_abstention_without_forcing_citation_metric(self) -> None:
        result = score_response(
            {
                "case_id": "RAG-DEV-002",
                "expected_response_type": "insufficient_evidence",
                "expected_document_ids": [],
            },
            {"response_type": "insufficient_evidence", "citations": []},
            latency_ms=20,
        )

        self.assertTrue(result["abstention_correct"])
        self.assertIsNone(result["citation_precision"])
        self.assertIsNone(result["citation_recall"])

    def test_aggregate_results_ignores_not_applicable_citation_values(self) -> None:
        answered = score_response(
            {
                "case_id": "RAG-DEV-001",
                "expected_response_type": "answered",
                "expected_document_ids": ["aks:E0000003"],
            },
            {"response_type": "answered", "citations": [{"document_id": "aks:E0000003"}]},
            latency_ms=100,
        )
        refused = score_response(
            {
                "case_id": "RAG-DEV-002",
                "expected_response_type": "safety_refusal",
                "expected_document_ids": [],
            },
            {"response_type": "safety_refusal", "citations": []},
            latency_ms=20,
        )

        summary = aggregate_results([answered, refused])

        self.assertEqual(summary["case_count"], 2)
        self.assertEqual(summary["response_type_accuracy"], 1.0)
        self.assertEqual(summary["abstention_accuracy"], 1.0)
        self.assertEqual(summary["mean_citation_precision"], 1.0)
        self.assertEqual(summary["mean_latency_ms"], 60.0)

    def test_rejects_unknown_response_type(self) -> None:
        with self.assertRaises(ValueError):
            score_response(
                {
                    "case_id": "RAG-DEV-003",
                    "expected_response_type": "made_up",
                    "expected_document_ids": [],
                },
                {"response_type": "answered", "citations": []},
                latency_ms=1,
            )


if __name__ == "__main__":
    unittest.main()
