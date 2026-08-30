from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from aks_data.config import load_project_env  # noqa: E402
from rag_indexing.pinecone_store import PineconeRetriever  # noqa: E402


DEFAULT_CASES = PROJECT_ROOT / "data" / "evaluation" / "aks_retrieval_eval_v1.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "aks_retrieval_eval_v1_result.json"


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        case = json.loads(line)
        required = {"case_id", "question", "expected_document_id", "expected_title", "category"}
        missing = required - case.keys()
        if missing:
            raise ValueError(f"{path}:{line_number} missing fields: {', '.join(sorted(missing))}")
        cases.append(case)
    if not cases:
        raise ValueError(f"No evaluation cases found in {path}")
    return cases


def score_case(case: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    expected_document_id = case["expected_document_id"]
    hit_rank = next(
        (result["retrieval_rank"] for result in results if result["document_id"] == expected_document_id),
        None,
    )
    return {
        **case,
        "hit_rank": hit_rank,
        "reciprocal_rank": (1 / hit_rank) if hit_rank else 0.0,
        "top_results": [
            {
                "rank": result["retrieval_rank"],
                "document_id": result["document_id"],
                "title": result["title"],
                "section": result["section"],
                "score": result["retrieval_score"],
            }
            for result in results
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate AKS Pinecone retrieval with human-labelled questions.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error("--top-k must be at least 1")

    load_project_env(PROJECT_ROOT / ".env")
    cases = load_cases(args.cases)
    retriever = PineconeRetriever()
    evaluations: list[dict[str, Any]] = []
    durations: list[float] = []
    for number, case in enumerate(cases, start=1):
        started_at = perf_counter()
        results = retriever.search(case["question"], top_k=args.top_k)
        durations.append(perf_counter() - started_at)
        evaluated = score_case(case, results)
        evaluations.append(evaluated)
        hit = f"{evaluated['hit_rank']}위" if evaluated["hit_rank"] else f"top-{args.top_k} 실패"
        print(f"[{number}/{len(cases)}] {case['case_id']}: {hit}")

    total = len(evaluations)
    recall_at_k = sum(item["hit_rank"] is not None for item in evaluations) / total
    mrr = sum(item["reciprocal_rank"] for item in evaluations) / total
    report = {
        "index_name": retriever.index_name,
        "embedding_model": retriever.embedding_model,
        "top_k": args.top_k,
        "case_count": total,
        "recall_at_k": recall_at_k,
        "mrr": mrr,
        "mean_query_seconds": sum(durations) / total,
        "evaluations": evaluations,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in report if key != "evaluations"}, ensure_ascii=False, indent=2))
    print(f"상세 결과: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
