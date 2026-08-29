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
from rag_indexing.pinecone_store import _require_env  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the number of AKS vectors stored in Pinecone.")
    parser.add_argument("--expected", type=int, default=179_028, help="Expected vector count after a complete upload.")
    parser.add_argument("--namespace", default="", help="Namespace to verify; empty string means Pinecone default namespace.")
    args = parser.parse_args()
    load_project_env(PROJECT_ROOT / ".env")

    try:
        from pinecone import Pinecone
    except ImportError as exc:
        raise RuntimeError("Install requirements.txt before checking Pinecone.") from exc

    index_name = _require_env("PINECONE_INDEX_NAME")
    index = Pinecone(api_key=_require_env("PINECONE_API_KEY")).Index(index_name)
    stats = index.describe_index_stats()
    namespaces = getattr(stats, "namespaces", None) or {}
    namespace_stats = namespaces.get(args.namespace)
    total = int(getattr(namespace_stats, "vector_count", 0))
    print(
        json.dumps(
            {
                "index_name": index_name,
                "namespace": args.namespace,
                "expected_vector_count": args.expected,
                "actual_vector_count": total,
                "status": "MATCH" if total == args.expected else "CHECK_REQUIRED",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if total == args.expected else 1


if __name__ == "__main__":
    raise SystemExit(main())
