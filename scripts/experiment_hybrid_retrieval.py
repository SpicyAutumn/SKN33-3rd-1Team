from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from statistics import fmean
import sys
from time import perf_counter
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aks_data.config import load_project_env  # noqa: E402
from evaluation.case_loader import load_evaluation_cases  # noqa: E402
from rag_indexing.bm25_store import BM25Retriever  # noqa: E402
from rag_indexing.hybrid_retriever import reciprocal_rank_fusion  # noqa: E402
from rag_indexing.pinecone_store import PineconeRetriever  # noqa: E402


DEFAULT_CASES = PROJECT_ROOT / "data" / "evaluation" / "aks_rag_dev_v1.jsonl"
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "processed" / "aks_bm25_v1.sqlite3"
DEFAULT_CACHE = PROJECT_ROOT / "outputs" / "aks_hybrid_candidate_cache.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "aks_hybrid_experiment_matrix.json"
RETRIEVAL_TYPES = {"answered", "corrected_premise"}
SCORE_DISTRIBUTION_TYPES = RETRIEVAL_TYPES | {"out_of_scope"}


def percentile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * ratio
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def describe(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "min": min(values) if values else None,
        "p25": percentile(values, 0.25),
        "median": percentile(values, 0.5),
        "p75": percentile(values, 0.75),
        "max": max(values) if values else None,
        "mean": fmean(values) if values else None,
    }


def collect_candidates(
    cases: list[dict[str, Any]],
    *,
    dense: PineconeRetriever,
    bm25: BM25Retriever,
    candidate_k: int,
) -> dict[str, Any]:
    collected: dict[str, Any] = {}
    for number, case in enumerate(cases, start=1):
        started = perf_counter()
        dense_results = dense.search(case["question"], top_k=candidate_k)
        dense_seconds = perf_counter() - started
        started = perf_counter()
        bm25_results = bm25.search(case["question"], top_k=candidate_k)
        bm25_seconds = perf_counter() - started
        collected[case["case_id"]] = {
            "dense": dense_results,
            "bm25": bm25_results,
            "dense_seconds": dense_seconds,
            "bm25_seconds": bm25_seconds,
        }
        print(f"[{number}/{len(cases)}] {case['case_id']} 후보 수집 완료", flush=True)
    return collected


def load_or_collect_candidates(
    cases: list[dict[str, Any]],
    *,
    cache_path: Path,
    bm25_path: Path,
    candidate_k: int,
    refresh: bool,
) -> dict[str, Any]:
    if cache_path.is_file() and not refresh:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        if cache.get("candidate_k") != candidate_k:
            raise ValueError(
                f"candidate cache uses candidate_k={cache.get('candidate_k')}, expected {candidate_k}; "
                "pass --refresh-cache"
            )
        expected_ids = {case["case_id"] for case in cases}
        if set(cache.get("cases", {})) != expected_ids:
            raise ValueError("candidate cache cases differ from the selected evaluation cases; pass --refresh-cache")
        return cache

    dense = PineconeRetriever()
    bm25 = BM25Retriever(bm25_path)
    candidates = collect_candidates(cases, dense=dense, bm25=bm25, candidate_k=candidate_k)
    cache = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_k": candidate_k,
        "cases": candidates,
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return cache


def score_case(
    case: dict[str, Any],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_ids = set(case.get("expected_document_ids", []))
    hit_rank = next(
        (result["retrieval_rank"] for result in results if result["document_id"] in expected_ids),
        None,
    )
    document_counts = Counter(str(result["document_id"]) for result in results)
    return {
        "case_id": case["case_id"],
        "response_type": case["expected_response_type"],
        "hit_rank": hit_rank,
        "reciprocal_rank": 1 / hit_rank if hit_rank else 0.0,
        "distinct_document_count": len(document_counts),
        "max_chunks_from_one_document": max(document_counts.values(), default=0),
        "results": [
            {
                "rank": result["retrieval_rank"],
                "chunk_id": result["chunk_id"],
                "document_id": result["document_id"],
                "title": result["title"],
                "rrf_score": result["retrieval_score"],
                "is_expected": result["document_id"] in expected_ids,
            }
            for result in results
        ],
    }


def evaluate_configuration(
    cases: list[dict[str, Any]],
    cache: dict[str, Any],
    *,
    name: str,
    candidate_k: int,
    top_k: int,
    dense_weight: float,
    bm25_weight: float,
    max_chunks_per_document: int | None,
) -> dict[str, Any]:
    evaluations: list[dict[str, Any]] = []
    for case in cases:
        cached = cache["cases"][case["case_id"]]
        results = reciprocal_rank_fusion(
            cached["dense"][:candidate_k],
            cached["bm25"][:candidate_k],
            top_k=top_k,
            rrf_k=60,
            dense_weight=dense_weight,
            bm25_weight=bm25_weight,
            max_chunks_per_document=max_chunks_per_document,
        )
        evaluations.append(score_case(case, results))

    count = len(evaluations)
    return {
        "name": name,
        "candidate_k": candidate_k,
        "top_k": top_k,
        "dense_weight": dense_weight,
        "bm25_weight": bm25_weight,
        "max_chunks_per_document": max_chunks_per_document,
        "case_count": count,
        "hit_at_1": sum(item["hit_rank"] == 1 for item in evaluations) / count,
        "hit_at_k": sum(item["hit_rank"] is not None for item in evaluations) / count,
        "mrr": fmean(item["reciprocal_rank"] for item in evaluations),
        "mean_distinct_documents": fmean(item["distinct_document_count"] for item in evaluations),
        "cases_with_duplicate_documents": sum(
            item["distinct_document_count"] < top_k for item in evaluations
        ),
        "max_chunks_from_one_document": max(
            item["max_chunks_from_one_document"] for item in evaluations
        ),
        "evaluations": evaluations,
    }


def score_distribution(
    cases: list[dict[str, Any]],
    cache: dict[str, Any],
) -> dict[str, dict[str, float | int | None]]:
    groups: dict[str, list[float]] = {
        "correct": [],
        "incorrect": [],
        "out_of_scope": [],
    }
    for case in cases:
        if case["expected_response_type"] not in SCORE_DISTRIBUTION_TYPES:
            continue
        cached = cache["cases"][case["case_id"]]
        results = reciprocal_rank_fusion(
            cached["dense"][:10],
            cached["bm25"][:10],
            top_k=3,
            rrf_k=60,
            dense_weight=1.5,
            bm25_weight=1.0,
        )
        if case["expected_response_type"] == "out_of_scope":
            groups["out_of_scope"].extend(float(result["retrieval_score"]) for result in results)
            continue
        expected_ids = set(case["expected_document_ids"])
        for result in results:
            group = "correct" if result["document_id"] in expected_ids else "incorrect"
            groups[group].append(float(result["retrieval_score"]))
    return {name: describe(values) for name, values in groups.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the agreed AKS hybrid retrieval experiment matrix.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--bm25-database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--refresh-cache", action="store_true")
    args = parser.parse_args()

    load_project_env(args.env_file)
    all_cases = load_evaluation_cases(args.cases, expected_split="dev")
    candidate_cases = [
        case for case in all_cases if case["expected_response_type"] in SCORE_DISTRIBUTION_TYPES
    ]
    retrieval_cases = [
        case for case in candidate_cases if case["expected_response_type"] in RETRIEVAL_TYPES
    ]
    cache = load_or_collect_candidates(
        candidate_cases,
        cache_path=args.cache,
        bm25_path=args.bm25_database,
        candidate_k=25,
        refresh=args.refresh_cache,
    )

    configurations: list[dict[str, Any]] = [
        {
            "name": "baseline",
            "candidate_k": 10,
            "top_k": 3,
            "dense_weight": 1.5,
            "bm25_weight": 1.0,
            "max_chunks_per_document": None,
        }
    ]
    configurations.extend(
        {
            "name": f"document_limit_{limit if limit is not None else 'none'}",
            "candidate_k": 10,
            "top_k": 3,
            "dense_weight": 1.5,
            "bm25_weight": 1.0,
            "max_chunks_per_document": limit,
        }
        for limit in (None, 2, 1)
    )
    configurations.extend(
        {
            "name": f"top_k_{top_k}",
            "candidate_k": 10,
            "top_k": top_k,
            "dense_weight": 1.5,
            "bm25_weight": 1.0,
            "max_chunks_per_document": None,
        }
        for top_k in (3, 5)
    )
    configurations.extend(
        {
            "name": f"candidate_k_{candidate_k}",
            "candidate_k": candidate_k,
            "top_k": 3,
            "dense_weight": 1.5,
            "bm25_weight": 1.0,
            "max_chunks_per_document": None,
        }
        for candidate_k in (5, 10, 20, 25)
    )
    configurations.extend(
        {
            "name": f"dense_weight_{dense_weight}",
            "candidate_k": 10,
            "top_k": 3,
            "dense_weight": dense_weight,
            "bm25_weight": 1.0,
            "max_chunks_per_document": None,
        }
        for dense_weight in (1.0, 1.5, 2.0, 2.5)
    )

    seen: set[tuple[Any, ...]] = set()
    experiments: list[dict[str, Any]] = []
    for config in configurations:
        signature = (
            config["candidate_k"],
            config["top_k"],
            config["dense_weight"],
            config["bm25_weight"],
            config["max_chunks_per_document"],
        )
        if signature in seen:
            continue
        seen.add(signature)
        experiments.append(evaluate_configuration(retrieval_cases, cache, **config))

    report = {
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "cases_file": str(args.cases),
        "retrieval_case_count": len(retrieval_cases),
        "score_distribution_case_count": len(candidate_cases),
        "reproducibility": {
            "candidate_cache": str(args.cache),
            "bm25_database": str(args.bm25_database),
            "pinecone_index": os.getenv("PINECONE_INDEX_NAME") or None,
            "pinecone_namespace": os.getenv("PINECONE_NAMESPACE") or "__default__",
            "embedding_model": os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        },
        "experiments": experiments,
        "baseline_rrf_score_distribution": score_distribution(candidate_cases, cache),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = [
        {
            key: experiment[key]
            for key in (
                "name",
                "candidate_k",
                "top_k",
                "dense_weight",
                "bm25_weight",
                "max_chunks_per_document",
                "hit_at_1",
                "hit_at_k",
                "mrr",
                "mean_distinct_documents",
                "cases_with_duplicate_documents",
            )
        }
        for experiment in experiments
    ]
    print(json.dumps({"experiments": summary, "score_distribution": report["baseline_rrf_score_distribution"]}, ensure_ascii=False, indent=2))
    print(f"상세 결과: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
