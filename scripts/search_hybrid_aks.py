from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aks_data.config import load_project_env  # noqa: E402
from rag_indexing.bm25_store import BM25Retriever  # noqa: E402
from rag_indexing.hybrid_retriever import HybridRetriever  # noqa: E402
from rag_indexing.pinecone_store import PineconeRetriever  # noqa: E402


DEFAULT_DATABASE = PROJECT_ROOT / "data" / "processed" / "aks_bm25_v1.sqlite3"


def main() -> int:
    parser = argparse.ArgumentParser(description="Search AKS with BM25 + Pinecone dense retrieval and RRF.")
    parser.add_argument("question")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--candidate-k", type=int, default=10)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--dense-weight", type=float, default=1.5)
    parser.add_argument("--bm25-weight", type=float, default=1.0)
    parser.add_argument("--bm25-database", type=Path, default=DEFAULT_DATABASE)
    args = parser.parse_args()

    load_project_env(PROJECT_ROOT / ".env")
    retriever = HybridRetriever(
        PineconeRetriever(),
        BM25Retriever(args.bm25_database),
        candidate_k=args.candidate_k,
        rrf_k=args.rrf_k,
        dense_weight=args.dense_weight,
        bm25_weight=args.bm25_weight,
    )
    results = retriever.search(args.question, top_k=args.top_k)
    print(json.dumps({"question": args.question, "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
