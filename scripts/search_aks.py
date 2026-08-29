from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from aks_data.config import load_project_env  # noqa: E402
from rag_indexing.pinecone_store import PineconeRetriever  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Search the AKS Pinecone index and print RetrievedContext JSON.")
    parser.add_argument("question")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    load_project_env(PROJECT_ROOT / ".env")
    results = PineconeRetriever().search(args.question, top_k=args.top_k)
    print(json.dumps({"question": args.question, "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
