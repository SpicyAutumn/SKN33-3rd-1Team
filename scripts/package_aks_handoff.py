from __future__ import annotations

import csv
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aks_data.core import load_article_csv  # noqa: E402


RAW_ARCHIVE_NAME = "aks_raw_api_first10000_20260828.zip"
CSV_ARCHIVE_NAME = "aks_source_csv_20240130.zip"
COLLECTION_MANIFEST_NAME = "manifest_collection_first10000.csv"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    raw_dir = PROJECT_ROOT / "data" / "raw"
    article_csv = next(path for path in raw_dir.glob("*.csv") if "한국민족문화대백과사전_20240130" in path.name)
    items = load_article_csv(article_csv)
    selected_eids = sorted({item.eid for item in items if item.eid})[:10000]
    manifest_path = PROJECT_ROOT / "data" / "manifest.csv"
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        manifest_by_eid = {row.get("eid", ""): row for row in reader}
    collection_rows = [manifest_by_eid[eid] for eid in selected_eids if eid in manifest_by_eid]
    handoff_dir = PROJECT_ROOT / "data" / "handoff"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    collection_manifest = handoff_dir / COLLECTION_MANIFEST_NAME
    with collection_manifest.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(collection_rows)

    raw_archive = handoff_dir / RAW_ARCHIVE_NAME
    with zipfile.ZipFile(raw_archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for eid in selected_eids:
            raw_json = raw_dir / "api" / f"{eid}.json"
            if raw_json.is_file():
                archive.write(raw_json, arcname=f"api/{raw_json.name}")
        archive.write(collection_manifest, arcname=COLLECTION_MANIFEST_NAME)
        archive.write(PROJECT_ROOT / "outputs" / "api_collection_validation.json", arcname="api_collection_validation.json")
        archive.write(PROJECT_ROOT / "outputs" / "api_collection_validation.md", arcname="api_collection_validation.md")
        archive.writestr(
            "README.txt",
            "Corpus filter: raw_file_path starts with data/raw/api/, has_body=true, status in {ok, warning}.\n"
            "This archive contains 9,962 stored raw JSON responses and a 10,000-EID collection manifest.\n"
            "Use the manifest filter above: the current usable body corpus has 9,960 items.\n",
        )

    csv_archive = handoff_dir / CSV_ARCHIVE_NAME
    with zipfile.ZipFile(csv_archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.write(article_csv, arcname=article_csv.name)

    checksums = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_archive": {"path": raw_archive.name, "sha256": sha256_file(raw_archive), "bytes": raw_archive.stat().st_size},
        "csv_archive": {"path": csv_archive.name, "sha256": sha256_file(csv_archive), "bytes": csv_archive.stat().st_size},
        "collection_manifest": {"path": collection_manifest.name, "sha256": sha256_file(collection_manifest)},
    }
    checksum_path = handoff_dir / "checksums.json"
    checksum_path.write_text(json.dumps(checksums, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, metadata in checksums.items():
        if isinstance(metadata, dict) and "sha256" in metadata:
            print(f"{name}={metadata['path']} sha256={metadata['sha256']} bytes={metadata.get('bytes', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
