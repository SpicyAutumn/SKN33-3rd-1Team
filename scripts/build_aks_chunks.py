from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rag_indexing.pipeline import ChunkingConfig, build_chunks, load_aks_jsonl, write_chunks_jsonl  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic AKS retrieval corpus from delivered JSONL.")
    parser.add_argument("--input", type=Path, required=True, help="Path to the delivered AKS JSONL file.")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data" / "processed" / "aks_chunks.jsonl")
    parser.add_argument("--report", type=Path, default=PROJECT_ROOT / "outputs" / "aks_chunking_report.json")
    parser.add_argument("--limit", type=int, default=10_000, help="Maximum successful source documents to process.")
    parser.add_argument("--max-chars", type=int, default=1_500)
    parser.add_argument("--overlap-chars", type=int, default=200)
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"input file does not exist: {args.input}")

    config = ChunkingConfig(max_chars=args.max_chars, overlap_chars=args.overlap_chars)
    payloads = list(load_aks_jsonl(args.input, limit=args.limit))
    chunks = build_chunks(payloads, config)
    count = write_chunks_jsonl(args.output, chunks)
    sections = Counter(chunk.section or "(none)" for chunk in chunks)
    report = {
        "input_path": str(args.input),
        "document_limit": args.limit,
        "successful_documents_processed": len(payloads),
        "documents_with_at_least_one_chunk": len({chunk.document_id for chunk in chunks}),
        "chunks_written": count,
        "chunks_by_section": dict(sorted(sections.items())),
        "chunking": {"max_chars": config.max_chars, "overlap_chars": config.overlap_chars, "version": config.version},
        "output_path": str(args.output),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
