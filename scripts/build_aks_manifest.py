"""AKS 상세 원본 JSON을 검증하고 추적 가능한 manifest를 생성한다."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "api"
MANIFEST_PATH = PROJECT_ROOT / "data" / "manifest.csv"
AUDIT_PATH = PROJECT_ROOT / "outputs" / "aks_raw_validation.json"
REPORT_PATH = PROJECT_ROOT / "outputs" / "aks_raw_validation_report.md"
JSONL_PATH = PROJECT_ROOT / "data" / "raw" / "aks_full_content.jsonl"
API_BASE_URL = "https://devin.aks.ac.kr:8080/api"

MANIFEST_COLUMNS = [
    "document_id", "eid", "api_title", "api_field",
    "item_type", "period", "keywords", "source_url", "api_url", "raw_file_path",
    "collected_at", "checksum", "content_length", "has_body", "license_note",
    "attribution", "status", "error",
]

LICENSE_NOTE = (
    "한국민족문화대백과사전 텍스트는 한국학중앙연구원 콘텐츠 이용 안내와 "
    "공공저작물 이용 조건을 확인하여 이용한다. 미디어는 항목별 권리 조건이 다르므로 제외한다."
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def values(value: Any, field: str | None = None) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        candidate = item.get(field) if field and isinstance(item, dict) else item
        candidate_text = text(candidate)
        if candidate_text and candidate_text not in result:
            result.append(candidate_text)
    return result


def manifest_row(path: Path, payload: dict[str, Any], error: str = "") -> dict[str, str]:
    file_eid = path.stem
    eid = text(payload.get("eid")) or file_eid
    title = text(payload.get("headword"))
    body = text(payload.get("body"))
    aliases = values(payload.get("articleAliases"), "word")
    hashtags = values(payload.get("hashtags"))
    keywords = ";".join(dict.fromkeys([*hashtags, *aliases]))
    source_url = text(payload.get("url")) or f"https://encykorea.aks.ac.kr/Article/{eid}"
    mismatch_error = "" if file_eid == eid else f"filename_eid_mismatch:{file_eid}!={eid}"
    all_errors = "; ".join(part for part in [error, mismatch_error] if part)
    status = "error" if all_errors else ("ok" if body else "warning")
    if not body and not all_errors:
        all_errors = "body_missing"

    return {
        "document_id": f"aks:{eid}",
        "eid": eid,
        "api_title": title,
        "api_field": text(payload.get("field")),
        "item_type": text(payload.get("primaryType")),
        "period": text(payload.get("era")),
        "keywords": keywords,
        "source_url": source_url,
        "api_url": f"{API_BASE_URL}/articles/{eid}",
        "raw_file_path": path.relative_to(PROJECT_ROOT).as_posix(),
        "collected_at": datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
        "checksum": sha256(path),
        "content_length": str(len(body)),
        "has_body": str(bool(body)).lower(),
        "license_note": LICENSE_NOTE,
        "attribution": f"출처: {title or eid} - 한국민족문화대백과사전 (한국학중앙연구원)",
        "status": status,
        "error": all_errors,
    }


def verify_jsonl(jsonl_path: Path, expected_eids: set[str]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": jsonl_path.relative_to(PROJECT_ROOT).as_posix(), "exists": jsonl_path.exists(),
        "lines": 0, "invalid_lines": 0, "duplicate_eids": 0, "unknown_eids": 0, "missing_eids": 0,
    }
    if not jsonl_path.exists():
        return result

    seen: set[str] = set()
    with jsonl_path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            result["lines"] += 1
            try:
                payload = json.loads(line)
                eid = text(payload.get("eid"))
                if not eid:
                    raise ValueError("eid_missing")
            except (json.JSONDecodeError, ValueError):
                result["invalid_lines"] += 1
                continue
            if eid in seen:
                result["duplicate_eids"] += 1
            seen.add(eid)
            if eid not in expected_eids:
                result["unknown_eids"] += 1
    result["missing_eids"] = len(expected_eids - seen)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="AKS 상세 원본 검증 및 manifest 생성")
    parser.add_argument("--verify-jsonl", action="store_true", help="aks_full_content.jsonl의 EID·줄 수까지 검증")
    args = parser.parse_args()

    json_files = sorted(RAW_DIR.glob("E*.json"))
    if not json_files:
        raise SystemExit(f"상세 JSON이 없습니다: {RAW_DIR}")

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_manifest = MANIFEST_PATH.with_suffix(".csv.tmp")
    seen_eids: set[str] = set()
    duplicate_eids: list[str] = []
    problems: list[dict[str, str]] = []
    stats: Counter[str] = Counter(files_scanned=len(json_files))

    with temporary_manifest.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        for index, path in enumerate(json_files, start=1):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("root_not_object")
                row = manifest_row(path, payload)
            except (OSError, ValueError, json.JSONDecodeError) as error:
                row = manifest_row(path, {}, f"invalid_json:{error}")

            if row["eid"] in seen_eids:
                duplicate_eids.append(row["eid"])
                row["status"] = "error"
                row["error"] = "; ".join(part for part in [row["error"], "duplicate_eid"] if part)
            seen_eids.add(row["eid"])
            writer.writerow(row)
            stats[row["status"]] += 1
            if row["error"] and len(problems) < 1000:
                problems.append({"eid": row["eid"], "file": row["raw_file_path"], "error": row["error"]})
            if index % 1000 == 0 or index == len(json_files):
                print(f"검증: {index}/{len(json_files)}, ok {stats['ok']}, warning {stats['warning']}, error {stats['error']}", flush=True)

    temporary_manifest.replace(MANIFEST_PATH)
    temp_files = sorted(path.relative_to(PROJECT_ROOT).as_posix() for path in RAW_DIR.glob("*.tmp"))
    for status in ("ok", "warning", "error"):
        stats[status] += 0
    audit: dict[str, Any] = {
        "source": "AKS OpenAPI GET /api/articles/{eid}",
        "raw_directory": RAW_DIR.relative_to(PROJECT_ROOT).as_posix(),
        "manifest": MANIFEST_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "stats": dict(stats),
        "unique_eids": len(seen_eids),
        "duplicate_eids": sorted(set(duplicate_eids)),
        "temporary_files": temp_files,
        "problems": problems,
    }
    if args.verify_jsonl:
        audit["jsonl_validation"] = verify_jsonl(JSONL_PATH, seen_eids)

    AUDIT_PATH.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    report = [
        "# AKS 원본 데이터 검증 결과", "",
        f"- 검사 JSON: {len(json_files):,}건", f"- 정상: {stats['ok']:,}건",
        f"- 본문 누락 경고: {stats['warning']:,}건", f"- 오류: {stats['error']:,}건",
        f"- 중복 EID: {len(set(duplicate_eids)):,}건", f"- 임시 파일: {len(temp_files):,}개",
        f"- manifest: `{MANIFEST_PATH.relative_to(PROJECT_ROOT).as_posix()}`",
    ]
    if args.verify_jsonl:
        jsonl = audit["jsonl_validation"]
        report.extend(["", "## JSONL 검증", "", f"- 줄 수: {jsonl['lines']:,}", f"- 잘못된 줄: {jsonl['invalid_lines']:,}", f"- 누락 EID: {jsonl['missing_eids']:,}"])
    REPORT_PATH.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"완료: {MANIFEST_PATH}")
    print(f"검증 결과: {AUDIT_PATH}")
    return 0 if stats["error"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
