from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from evaluation import load_evaluation_cases, summarize_cases  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate RAG dev and holdout JSONL case files.")
    parser.add_argument(
        "--dev",
        type=Path,
        default=PROJECT_ROOT / "data" / "evaluation" / "aks_rag_dev_v1.jsonl",
    )
    parser.add_argument(
        "--holdout",
        type=Path,
        default=PROJECT_ROOT / "data" / "evaluation" / "aks_rag_holdout_v1.jsonl",
    )
    args = parser.parse_args()

    report = {
        "dev": summarize_cases(load_evaluation_cases(args.dev, expected_split="dev")),
        "holdout": summarize_cases(load_evaluation_cases(args.holdout, expected_split="holdout")),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
