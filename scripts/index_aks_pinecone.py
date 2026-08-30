from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aks_data.config import load_project_env  # noqa: E402
from rag_indexing.pinecone_store import PineconeRetriever  # noqa: E402
from rag_indexing.pipeline import Chunk  # noqa: E402


def load_chunks(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            value = json.loads(line)
            yield Chunk(**value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Embed and upsert AKS chunks into Pinecone.")
    parser.add_argument("--input", type=Path, default=PROJECT_ROOT / "data" / "processed" / "aks_chunks.jsonl")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument(
        "--namespace",
        help="Pinecone namespace. Overrides PINECONE_NAMESPACE; use a new name for a changed chunking scheme.",
    )
    parser.add_argument(
        "--allow-default-namespace",
        action="store_true",
        help="Allow v2 chunks in Pinecone's default namespace after deliberately clearing or migrating it.",
    )
    parser.add_argument("--limit", type=int, help="Maximum chunks to index; use 100 for the first paid test.")
    parser.add_argument(
        "--start-offset",
        type=int,
        help="Resume from this zero-based chunk offset without fetching existing vectors from Pinecone.",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "aks_embedding_checkpoint.json",
        help="Local progress checkpoint written after every successful Pinecone upsert.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate the corpus without calling external APIs.")
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Re-embed every input chunk even when it is already stored with the current input format.",
    )
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"chunk corpus does not exist: {args.input}")
    chunks = list(load_chunks(args.input))
    total_chunks = len(chunks)
    start_offset = args.start_offset or 0
    if not 0 <= start_offset <= total_chunks:
        parser.error("--start-offset must be between 0 and the number of input chunks")
    if start_offset:
        chunks = chunks[start_offset:]
    if args.limit is not None:
        if args.limit < 1:
            parser.error("--limit must be at least 1")
        chunks = chunks[: args.limit]
    if args.dry_run:
        print(
            json.dumps(
                {"chunks_ready": len(chunks), "start_offset": start_offset, "input_path": str(args.input)},
                ensure_ascii=False,
            )
        )
        return 0
    load_project_env(PROJECT_ROOT / ".env")
    namespace = args.namespace if args.namespace is not None else os.getenv("PINECONE_NAMESPACE", "")
    is_v2_corpus = any(chunk.metadata.get("chunk_id_schema_version") == "v2" for chunk in chunks)
    if is_v2_corpus and not namespace and not args.allow_default_namespace:
        parser.error(
            "v2 chunk IDs require a new --namespace (for example aks-chunk-v2). "
            "Use --allow-default-namespace only after deliberately clearing or migrating the default namespace."
        )
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(processed: int) -> None:
        absolute_offset = start_offset + processed
        args.checkpoint.write_text(
            json.dumps(
                {
                    "input_path": str(args.input),
                    "next_offset": absolute_offset,
                    "total_chunks": total_chunks,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        if processed == args.batch_size or absolute_offset % 500 == 0:
            print(f"로컬 진행 저장: {absolute_offset:,}/{total_chunks:,}", flush=True)

    # A known offset is safer than fetching 1,536-dimensional vectors just to check their metadata.
    result = PineconeRetriever(namespace=namespace).upsert(
        chunks,
        batch_size=args.batch_size,
        resume=not args.no_resume and start_offset == 0,
        progress_callback=save_checkpoint,
    )
    result["next_offset"] = start_offset + result["total"]
    result["namespace"] = namespace
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
