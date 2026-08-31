"""Validate a delivered AKS chunk JSONL file against the manifest when available."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_CHUNK_FIELDS = {
    "chunk_id",
    "document_id",
    "title",
    "content",
    "source_url",
    "section",
    "metadata",
}
ALLOWED_SECTIONS = {"definition", "body", None}
REQUIRED_METADATA_STRING_FIELDS = {
    "chunking_version",
    "document_fingerprint",
}
OPTIONAL_METADATA_STRING_FIELDS = {
    "chunking_fingerprint",
}
OPTIONAL_METADATA_INTEGER_FIELDS = {
    "chunking_max_chars",
    "chunking_overlap_chars",
}


def file_provenance(path: Path) -> dict[str, Any]:
    """Return reproducible identity details without loading a large file at once."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def load_expected_document_ids(path: Path) -> set[str]:
    """Return corpus-eligible document IDs from the current manifest format."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle)
        return {
            row["document_id"].strip()
            for row in rows
            if row.get("document_id")
            and row.get("has_body", "").strip().lower() == "true"
            and row.get("status", "").strip() == "ok"
        }


def validate_chunks(path: Path, expected_document_ids: set[str] | None) -> dict[str, Any]:
    stats: Counter[str] = Counter()
    seen_chunks: set[str] = set()
    seen_documents: set[str] = set()
    unexpected_documents: set[str] = set()
    examples: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                stats["blank_lines"] += 1
                continue
            stats["lines"] += 1
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                stats["invalid_json"] += 1
                if len(examples) < 20:
                    examples.append({"line": line_number, "error": "invalid_json"})
                continue

            if not isinstance(chunk, dict) or not REQUIRED_CHUNK_FIELDS.issubset(chunk):
                stats["invalid_schema"] += 1
                if len(examples) < 20:
                    examples.append({"line": line_number, "error": "missing_required_chunk_fields"})
                continue

            chunk_id = chunk["chunk_id"]
            document_id = chunk["document_id"]
            title = chunk["title"]
            content = chunk["content"]
            if not isinstance(chunk_id, str) or not chunk_id.strip():
                stats["invalid_chunk_id"] += 1
            elif chunk_id in seen_chunks:
                stats["duplicate_chunk_id"] += 1
            else:
                seen_chunks.add(chunk_id)

            if not isinstance(document_id, str) or not document_id.strip():
                stats["invalid_document_id"] += 1
            else:
                seen_documents.add(document_id)
                if expected_document_ids is not None and document_id not in expected_document_ids:
                    unexpected_documents.add(document_id)

            if not isinstance(title, str) or not title.strip():
                stats["invalid_title"] += 1
            if not isinstance(content, str) or not content.strip():
                stats["empty_content"] += 1

            source_url = chunk["source_url"]
            if source_url is not None and (not isinstance(source_url, str) or not source_url.strip()):
                stats["invalid_source_url"] += 1
            if chunk["section"] not in ALLOWED_SECTIONS:
                stats["invalid_section"] += 1

            metadata = chunk["metadata"]
            if not isinstance(metadata, dict):
                stats["invalid_metadata"] += 1
            else:
                if not isinstance(metadata.get("aliases"), list):
                    stats["invalid_metadata_values"] += 1
                for field in REQUIRED_METADATA_STRING_FIELDS:
                    if not isinstance(metadata.get(field), str) or not metadata[field].strip():
                        stats["invalid_metadata_values"] += 1
                for field in OPTIONAL_METADATA_STRING_FIELDS:
                    if field in metadata and (not isinstance(metadata[field], str) or not metadata[field].strip()):
                        stats["invalid_metadata_values"] += 1
                for field in OPTIONAL_METADATA_INTEGER_FIELDS:
                    if field in metadata and (
                        isinstance(metadata[field], bool) or not isinstance(metadata[field], int)
                    ):
                        stats["invalid_metadata_values"] += 1

    report: dict[str, Any] = {
        "input": str(path),
        "chunk_lines": stats["lines"],
        "blank_lines": stats["blank_lines"],
        "unique_chunk_ids": len(seen_chunks),
        "unique_document_ids": len(seen_documents),
        "invalid_json": stats["invalid_json"],
        "invalid_schema": stats["invalid_schema"],
        "duplicate_chunk_id": stats["duplicate_chunk_id"],
        "invalid_chunk_id": stats["invalid_chunk_id"],
        "invalid_document_id": stats["invalid_document_id"],
        "invalid_title": stats["invalid_title"],
        "empty_content": stats["empty_content"],
        "invalid_source_url": stats["invalid_source_url"],
        "invalid_section": stats["invalid_section"],
        "invalid_metadata": stats["invalid_metadata"],
        "invalid_metadata_values": stats["invalid_metadata_values"],
        "examples": examples,
    }
    if expected_document_ids is not None:
        report["manifest_eligible_document_ids"] = len(expected_document_ids)
        report["documents_missing_from_chunks"] = len(expected_document_ids - seen_documents)
        report["documents_not_eligible_in_manifest"] = len(unexpected_documents)
        report["unexpected_document_examples"] = sorted(unexpected_documents)[:20]
    return report


def has_failures(report: dict[str, Any], *, manifest_checked: bool) -> bool:
    """Return whether the selected validation mode found a corpus-integrity failure."""
    structural_failures = (
        "invalid_json",
        "invalid_schema",
        "duplicate_chunk_id",
        "invalid_chunk_id",
        "invalid_document_id",
        "invalid_title",
        "empty_content",
        "invalid_source_url",
        "invalid_section",
        "invalid_metadata",
        "invalid_metadata_values",
    )
    if any(int(report[key]) for key in structural_failures):
        return True
    return manifest_checked and (
        int(report["documents_missing_from_chunks"]) > 0
        or int(report["documents_not_eligible_in_manifest"]) > 0
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate AKS chunk JSONL and optional manifest eligibility.")
    parser.add_argument("--input", type=Path, required=True, help="Downloaded aks_full_chunks.jsonl path")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT_ROOT / "data" / "manifest.csv",
        help="Manifest used to check has_body=true and status=ok (omit with --no-manifest)",
    )
    parser.add_argument("--no-manifest", action="store_true", help="Only validate JSONL structure")
    parser.add_argument("--report", type=Path, default=None, help="Optional JSON report path")
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"input file does not exist: {args.input}")
    if not args.no_manifest and not args.manifest.is_file():
        parser.error(f"manifest file does not exist: {args.manifest}")
    expected_ids = None if args.no_manifest else load_expected_document_ids(args.manifest)
    report = validate_chunks(args.input, expected_ids)
    report["checked_at"] = datetime.now(timezone.utc).isoformat()
    report["input_file"] = file_provenance(args.input)
    report["manifest_file"] = None if args.no_manifest else file_provenance(args.manifest)
    report["validation_passed"] = not has_failures(report, manifest_checked=not args.no_manifest)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")

    return 0 if report["validation_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
