from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterator


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rag_indexing.bm25_store import build_bm25_index  # noqa: E402


DEFAULT_CHUNKS = PROJECT_ROOT / "data" / "processed" / "aks_chunks.jsonl"
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "processed" / "aks_bm25_v1.sqlite3"


def load_chunks(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number} is not valid JSONL") from exc
            if not isinstance(chunk, dict):
                raise ValueError(f"{path}:{line_number} must be a JSON object")
            yield chunk


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a local SQLite FTS5 BM25 index from AKS chunks.")
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--force", action="store_true", help="replace an existing generated BM25 index")
    args = parser.parse_args()
    if not args.chunks.is_file():
        parser.error(f"chunk JSONL not found: {args.chunks}")
    try:
        count = build_bm25_index(load_chunks(args.chunks), args.database, force=args.force)
    except FileExistsError as exc:
        parser.error(str(exc))
    print(json.dumps({"database": str(args.database), "chunk_count": count}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
