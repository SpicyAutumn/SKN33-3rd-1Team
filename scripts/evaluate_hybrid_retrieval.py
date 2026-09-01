from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aks_data.config import load_project_env  # noqa: E402
from evaluation.case_loader import load_evaluation_cases  # noqa: E402
from rag_indexing.bm25_store import BM25Retriever  # noqa: E402
from rag_indexing.hybrid_retriever import HybridRetriever, Retriever  # noqa: E402
from rag_indexing.pinecone_store import PineconeRetriever  # noqa: E402


DEFAULT_CASES = PROJECT_ROOT / "data" / "evaluation" / "aks_rag_dev_v1.jsonl"
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "processed" / "aks_bm25_v1.sqlite3"
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "aks_hybrid_retrieval_dev_result.json"
EVALUATED_RESPONSE_TYPES = {"answered", "corrected_premise"}


def select_retrieval_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [case for case in cases if case["expected_response_type"] in EVALUATED_RESPONSE_TYPES]


def load_bm25_manifest(database_path: Path) -> dict[str, Any] | None:
    path = database_path.with_suffix(f"{database_path.suffix}.manifest.json")
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"BM25 manifest is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"BM25 manifest must be a JSON object: {path}")
    return value


def evaluate(retriever: Retriever, cases: list[dict[str, Any]], *, top_k: int) -> dict[str, Any]:
    evaluations: list[dict[str, Any]] = []
    durations: list[float] = []
    for number, case in enumerate(cases, start=1):
        started_at = perf_counter()
        results = retriever.search(case["question"], top_k=top_k)
        durations.append(perf_counter() - started_at)
        expected_ids = set(case["expected_document_ids"])
        hit_rank = next(
            (item["retrieval_rank"] for item in results if item["document_id"] in expected_ids), None
        )
        evaluations.append(
            {
                "case_id": case["case_id"],
                "expected_response_type": case["expected_response_type"],
                "question": case["question"],
                "expected_document_ids": case["expected_document_ids"],
                "hit_rank": hit_rank,
                "reciprocal_rank": 1 / hit_rank if hit_rank else 0.0,
                "top_results": [
                    {
                        "rank": item["retrieval_rank"],
                        "document_id": item["document_id"],
                        "title": item["title"],
                        "score": item["retrieval_score"],
                        "score_type": item["score_type"],
                    }
                    for item in results
                ],
            }
        )
        hit = f"{hit_rank}위" if hit_rank else f"top-{top_k} 실패"
        print(f"[{number}/{len(cases)}] {case['case_id']}: {hit}", flush=True)

    count = len(evaluations)
    type_counts = Counter(item["expected_response_type"] for item in evaluations)
    type_hit_counts = {
        response_type: sum(
            item["hit_rank"] is not None
            for item in evaluations
            if item["expected_response_type"] == response_type
        )
        for response_type in sorted(type_counts)
    }
    return {
        "case_count": count,
        "response_type_counts": dict(sorted(type_counts.items())),
        "hit_at_k": sum(item["hit_rank"] is not None for item in evaluations) / count,
        "mrr": sum(item["reciprocal_rank"] for item in evaluations) / count,
        "mean_query_seconds": sum(durations) / count,
        "hits_by_response_type": type_hit_counts,
        "evaluations": evaluations,
    }


def evaluate_comparison(
    dense: Retriever, hybrid: HybridRetriever, cases: list[dict[str, Any]], *, top_k: int
) -> dict[str, dict[str, Any]]:
    """Compare both methods with one OpenAI query embedding per case."""

    dense_evaluations: list[dict[str, Any]] = []
    hybrid_evaluations: list[dict[str, Any]] = []
    dense_durations: list[float] = []
    hybrid_durations: list[float] = []
    candidate_k = max(top_k, hybrid.candidate_k)
    for number, case in enumerate(cases, start=1):
        started_at = perf_counter()
        dense_candidates = dense.search(case["question"], top_k=candidate_k)
        dense_durations.append(perf_counter() - started_at)
        dense_results = dense_candidates[:top_k]

        started_at = perf_counter()
        hybrid_results = hybrid.search_from_dense_results(case["question"], dense_candidates, top_k=top_k)
        hybrid_durations.append(perf_counter() - started_at)

        def scored(results: list[dict[str, Any]]) -> dict[str, Any]:
            expected_ids = set(case["expected_document_ids"])
            hit_rank = next(
                (item["retrieval_rank"] for item in results if item["document_id"] in expected_ids), None
            )
            return {
                "case_id": case["case_id"],
                "expected_response_type": case["expected_response_type"],
                "question": case["question"],
                "expected_document_ids": case["expected_document_ids"],
                "hit_rank": hit_rank,
                "reciprocal_rank": 1 / hit_rank if hit_rank else 0.0,
                "top_results": [
                    {
                        "rank": item["retrieval_rank"],
                        "document_id": item["document_id"],
                        "title": item["title"],
                        "score": item["retrieval_score"],
                        "score_type": item["score_type"],
                    }
                    for item in results
                ],
            }

        dense_result = scored(dense_results)
        hybrid_result = scored(hybrid_results)
        dense_evaluations.append(dense_result)
        hybrid_evaluations.append(hybrid_result)
        dense_hit = f"{dense_result['hit_rank']}위" if dense_result["hit_rank"] else f"top-{top_k} 실패"
        hybrid_hit = f"{hybrid_result['hit_rank']}위" if hybrid_result["hit_rank"] else f"top-{top_k} 실패"
        print(f"[{number}/{len(cases)}] {case['case_id']}: Dense {dense_hit} / Hybrid {hybrid_hit}", flush=True)

    def summarise(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
        count = len(evaluations)
        type_counts = Counter(item["expected_response_type"] for item in evaluations)
        return {
            "case_count": count,
            "response_type_counts": dict(sorted(type_counts.items())),
            "hit_at_k": sum(item["hit_rank"] is not None for item in evaluations) / count,
            "mrr": sum(item["reciprocal_rank"] for item in evaluations) / count,
            "hits_by_response_type": {
                response_type: sum(
                    item["hit_rank"] is not None
                    for item in evaluations
                    if item["expected_response_type"] == response_type
                )
                for response_type in sorted(type_counts)
            },
            "evaluations": evaluations,
        }

    return {
        "dense": {
            **summarise(dense_evaluations),
            "mean_query_seconds": sum(dense_durations) / len(dense_durations),
        },
        "hybrid": {
            **summarise(hybrid_evaluations),
            # Dense candidates are intentionally reused, so this measures only
            # the additional local BM25 + RRF work.
            "mean_additional_processing_seconds": sum(hybrid_durations) / len(hybrid_durations),
            "mean_total_query_seconds": sum(
                dense_duration + hybrid_duration
                for dense_duration, hybrid_duration in zip(dense_durations, hybrid_durations, strict=True)
            )
            / len(dense_durations),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare dense and BM25+RRF hybrid AKS retrieval on Dev cases.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--split", choices=("dev", "holdout"), default="dev")
    parser.add_argument("--bm25-database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--candidate-k", type=int, default=10)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--dense-weight", type=float, default=1.5)
    parser.add_argument("--bm25-weight", type=float, default=1.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error("--top-k must be at least 1")

    load_project_env(PROJECT_ROOT / ".env")
    cases = select_retrieval_cases(load_evaluation_cases(args.cases, expected_split=args.split))
    dense = PineconeRetriever()
    hybrid = HybridRetriever(
        dense,
        BM25Retriever(args.bm25_database),
        candidate_k=args.candidate_k,
        rrf_k=args.rrf_k,
        dense_weight=args.dense_weight,
        bm25_weight=args.bm25_weight,
    )
    comparison = evaluate_comparison(dense, hybrid, cases, top_k=args.top_k)
    report = {
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "cases_file": str(args.cases),
        "top_k": args.top_k,
        "candidate_k": args.candidate_k,
        "rrf_k": args.rrf_k,
        "dense_weight": args.dense_weight,
        "bm25_weight": args.bm25_weight,
        "reproducibility": {
            "bm25_database": str(args.bm25_database),
            "bm25_manifest": load_bm25_manifest(args.bm25_database),
            "pinecone_index": os.getenv("PINECONE_INDEX_NAME") or None,
            "pinecone_namespace": os.getenv("PINECONE_NAMESPACE") or "__default__",
            "embedding_model": os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        },
        **comparison,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "dense": {
            key: report["dense"][key]
            for key in ("case_count", "hit_at_k", "mrr", "mean_query_seconds")
        },
        "hybrid": {
            key: report["hybrid"][key]
            for key in ("case_count", "hit_at_k", "mrr", "mean_additional_processing_seconds", "mean_total_query_seconds")
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"상세 결과: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
