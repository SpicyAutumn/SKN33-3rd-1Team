from __future__ import annotations

import csv
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .api import AksApiClient, ApiRequestError, DEFAULT_API_BASE_URL, parse_article
from .core import (
    ATTRIBUTION_TEMPLATE,
    EID_RE,
    LICENSE_NOTE,
    CsvItem,
    analyze_csv,
    load_article_csv,
    normalize_text,
    sha256_bytes,
    stratified_sample,
    write_bytes_atomic,
    write_csv,
    write_json,
)


MANIFEST_COLUMNS = [
    "document_id",
    "eid",
    "csv_title",
    "api_title",
    "csv_field",
    "api_field",
    "item_type",
    "period",
    "keywords",
    "source_url",
    "api_url",
    "raw_file_path",
    "collected_at",
    "checksum",
    "content_length",
    "has_body",
    "license_note",
    "attribution",
    "status",
    "error",
]

COMPARISON_COLUMNS = MANIFEST_COLUMNS + [
    "csv_row_number",
    "sample_stratum",
    "response_eid",
    "eid_match",
    "title_match",
    "field_match",
    "api_only_fields",
    "response_root_fields",
]


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def relative_path(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _empty_parsed() -> dict[str, Any]:
    return {
        "eid": "",
        "title": "",
        "field": "",
        "body": "",
        "content_length": 0,
        "has_body": False,
        "item_type": "",
        "period": "",
        "keywords": "",
        "api_only_fields": [],
        "response_root_fields": [],
    }


def _record(
    item: CsvItem,
    *,
    parsed: dict[str, Any],
    api_url: str,
    raw_file_path: str,
    collected_at: str,
    checksum: str,
    status: str,
    error: str,
) -> dict[str, Any]:
    response_eid = parsed["eid"]
    api_title = parsed["title"]
    api_field = parsed["field"]
    return {
        "document_id": f"aks:{item.eid}",
        "eid": item.eid or "",
        "csv_title": item.title,
        "api_title": api_title,
        "csv_field": item.field,
        "api_field": api_field,
        "item_type": parsed["item_type"],
        "period": parsed["period"],
        "keywords": parsed["keywords"],
        "source_url": item.source_url,
        "api_url": api_url,
        "raw_file_path": raw_file_path,
        "collected_at": collected_at,
        "checksum": checksum,
        "content_length": parsed["content_length"],
        "has_body": str(bool(parsed["has_body"])).lower(),
        "license_note": LICENSE_NOTE,
        "attribution": ATTRIBUTION_TEMPLATE.format(title=api_title or item.title),
        "status": status,
        "error": error,
        "csv_row_number": item.row_number,
        "sample_stratum": item.stratum,
        "response_eid": response_eid,
        "eid_match": str(bool(response_eid) and response_eid == item.eid).lower() if response_eid else "",
        "title_match": str(bool(api_title) and normalize_text(api_title) == normalize_text(item.title)).lower() if api_title else "",
        "field_match": str(bool(api_field) and normalize_text(api_field) == normalize_text(item.field)).lower() if api_field else "",
        "api_only_fields": ";".join(parsed["api_only_fields"]),
        "response_root_fields": ";".join(parsed["response_root_fields"]),
    }


def _fetch_record(
    item: CsvItem,
    *,
    client: AksApiClient | None,
    api_base_url: str,
    raw_path: Path,
    project_root: Path,
) -> dict[str, Any]:
    timestamp = now_utc()
    api_url = f"{api_base_url.rstrip('/')}/articles/{item.eid}"
    if client is None:
        return _record(
            item,
            parsed=_empty_parsed(),
            api_url=api_url,
            raw_file_path="",
            collected_at=timestamp,
            checksum="",
            status="not_run",
            error="missing_api_key",
        )
    try:
        response = client.fetch_article(item.eid or "")
        write_bytes_atomic(raw_path, response.raw)
        parsed = parse_article(response.payload)
        eid_match = parsed["eid"] == item.eid
        title_match = normalize_text(parsed["title"]) == normalize_text(item.title)
        status = "ok" if eid_match and title_match and parsed["has_body"] else "warning"
        warnings: list[str] = []
        if not parsed["eid"]:
            warnings.append("api_eid_missing")
        elif not eid_match:
            warnings.append("eid_mismatch")
        if not parsed["title"]:
            warnings.append("api_title_missing")
        elif not title_match:
            warnings.append("title_mismatch")
        if not parsed["has_body"]:
            warnings.append("body_missing")
        return _record(
            item,
            parsed=parsed,
            api_url=response.api_url,
            raw_file_path=relative_path(raw_path, project_root),
            collected_at=timestamp,
            checksum=sha256_bytes(response.raw),
            status=status,
            error=";".join(warnings),
        )
    except (ApiRequestError, ValueError) as exc:
        reason = exc.reason if isinstance(exc, ApiRequestError) else str(exc)
        return _record(
            item,
            parsed=_empty_parsed(),
            api_url=api_url,
            raw_file_path="",
            collected_at=timestamp,
            checksum="",
            status="api_error",
            error=reason,
        )


def upsert_manifest(path: Path, new_rows: list[dict[str, Any]]) -> None:
    existing = load_manifest(path)
    merge_manifest_records(existing, new_rows)
    write_manifest(path, existing)


def load_manifest(path: Path) -> dict[str, dict[str, Any]]:
    existing: dict[str, dict[str, Any]] = {}
    if path.exists():
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                key = row.get("document_id") or row.get("eid") or ""
                if key:
                    existing[key] = row
    return existing


def merge_manifest_records(existing: dict[str, dict[str, Any]], new_rows: list[dict[str, Any]]) -> None:
    for row in new_rows:
        existing[str(row["document_id"])] = {key: row.get(key, "") for key in MANIFEST_COLUMNS}


def write_manifest(path: Path, existing: dict[str, dict[str, Any]]) -> None:
    ordered = sorted(existing.values(), key=lambda row: (row.get("eid", ""), row.get("document_id", "")))
    write_csv(path, ordered, MANIFEST_COLUMNS)


def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [row for row in records if row["status"] in {"ok", "warning"}]
    api_only_counts: Counter[str] = Counter()
    for row in successful:
        api_only_counts.update(filter(None, str(row["api_only_fields"]).split(";")))
    return {
        "sample_count": len(records),
        "status_counts": dict(sorted(Counter(str(row["status"]) for row in records).items())),
        "api_success_count": len(successful),
        "eid_match_count": sum(row["eid_match"] == "true" for row in successful),
        "title_match_count": sum(row["title_match"] == "true" for row in successful),
        "field_match_count": sum(row["field_match"] == "true" for row in successful),
        "body_present_count": sum(row["has_body"] == "true" for row in successful),
        "content_length": {
            "min": min((int(row["content_length"]) for row in successful), default=0),
            "max": max((int(row["content_length"]) for row in successful), default=0),
            "average": round(
                sum(int(row["content_length"]) for row in successful) / len(successful), 2
            )
            if successful
            else 0,
        },
        "api_only_field_counts": dict(sorted(api_only_counts.items())),
        "error_counts": dict(sorted(Counter(str(row["error"]) for row in records if row["error"]).items())),
    }


def _render_report(audit: dict[str, Any]) -> str:
    meta = audit["audit_metadata"]
    quality = audit["csv_quality"]
    summary = audit["comparison_summary"]
    allocations = meta["sample_allocation"]
    lines = [
        "# 한국민족문화대백과사전 CSV·OpenAPI 감사 보고서",
        "",
        f"- 실행 시각(UTC): `{meta['generated_at']}`",
        f"- 일반 항목 CSV: `{meta['article_csv']}`",
        f"- 미디어 CSV: 본문 감사 제외 ({meta['media_csv_count']}개 발견)",
        f"- 표본: `{meta['sample_size']}`건, seed `{meta['seed']}`",
        "- 층화 기준: CSV `분야`의 `/` 앞 대분야를 층으로 사용, 각 층 최소 1건 후 모집단 비율 배분",
        f"- API 기본 URL: `{meta['api_base_url']}`",
        "",
        "## CSV 품질",
        "",
        f"- 전체 행: {quality['row_count']:,}",
        f"- 유효 EID 행 / 고유 EID: {quality['valid_eid_rows']:,} / {quality['unique_eid_count']:,}",
        f"- 중복 EID 종류 / 중복 관련 행: {quality['duplicate_eid_count']:,} / {quality['duplicate_row_count']:,}",
        f"- 항목명 누락: {quality['missing_title_count']:,}",
        f"- 분야 누락: {quality['missing_field_count']:,}",
        f"- 누락·잘못된 URL: {quality['invalid_url_count']:,}",
        "",
        "## 표본 배분",
        "",
        "| 대분야 | 표본 수 |",
        "| :--- | ---: |",
    ]
    lines.extend(f"| {name} | {count} |" for name, count in allocations.items())
    lines.extend(
        [
            "",
            "## API 비교 요약",
            "",
            f"- 상태: {', '.join(f'`{key}` {value}건' for key, value in summary['status_counts'].items())}",
            f"- API 응답 성공: {summary['api_success_count']} / {summary['sample_count']}",
            f"- EID 일치: {summary['eid_match_count']} / {summary['api_success_count']}",
            f"- 제목 일치: {summary['title_match_count']} / {summary['api_success_count']}",
            f"- 분야 완전 일치: {summary['field_match_count']} / {summary['api_success_count']}",
            f"- 본문 존재: {summary['body_present_count']} / {summary['api_success_count']}",
            (
                "- 본문 길이(문자): 최소 {min:,}, 평균 {average:,.2f}, 최대 {max:,}".format(
                    **summary["content_length"]
                )
            ),
            "",
        ]
    )
    if summary["api_success_count"] == 0 and summary["error_counts"].get("missing_api_key"):
        lines.extend(
            [
                "> `AKS_API_KEY`가 없어 API 호출은 실행하지 않았습니다. 키 설정 후 같은 명령을 다시 실행하면 이 보고서가 갱신됩니다.",
                "",
            ]
        )
    lines.extend(
        [
            "## 해석과 제한",
            "",
            "- CSV는 항목명·분야·웹 URL의 목록 단위이고, API는 본문과 추가 메타데이터를 제공하는 상세 단위다.",
            "- 분야 비교는 문자열 완전 일치로 계산한다. API가 대분야와 세부분야를 분리해 제공하면 차이는 오류가 아니라 스키마 차이일 수 있다.",
            "- 미디어 CSV는 항목 EID·본문이 없는 별도 단위이며 권리자가 자료마다 다를 수 있어 이번 수집에서 제외했다.",
            "- 상세 행과 오류 사유는 `outputs/csv_api_comparison.csv`, 기계 판독 결과는 `outputs/csv_api_audit.json`에서 확인한다.",
            "",
            "## 저작권·출처",
            "",
            "항목 본문은 한국학중앙연구원이 저작재산권 전부를 보유한 저작물 범위에서 자유이용할 수 있다. 출처는 "
            "`[항목명],『한국민족문화대백과사전』` 형식으로 표시한다. 미디어는 공공누리 마크가 있는 자료만 해당 조건으로 "
            "이용할 수 있고, 마크가 없는 자료는 별도 권리자의 허가가 필요하다.",
            "",
        ]
    )
    return "\n".join(lines)


def run_audit(
    *,
    project_root: Path,
    csv_path: Path,
    media_paths: list[Path],
    api_key: str,
    api_base_url: str = DEFAULT_API_BASE_URL,
    sample_size: int = 25,
    seed: int = 20260828,
    timeout: float = 30.0,
    retries: int = 2,
) -> dict[str, Any]:
    if not 20 <= sample_size <= 30:
        raise ValueError("감사 표본 크기는 요구 범위인 20~30이어야 합니다.")
    items = load_article_csv(csv_path)
    quality = analyze_csv(items)
    sample, allocation = stratified_sample(items, sample_size, seed)
    client = (
        AksApiClient(api_key, api_base_url, timeout=timeout, retries=retries)
        if api_key.strip()
        else None
    )
    audit_raw_dir = project_root / "data" / "raw" / "api_audit"
    records = [
        _fetch_record(
            item,
            client=client,
            api_base_url=api_base_url,
            raw_path=audit_raw_dir / f"{item.eid}.json",
            project_root=project_root,
        )
        for item in sample
    ]
    comparison_path = project_root / "outputs" / "csv_api_comparison.csv"
    write_csv(comparison_path, records, COMPARISON_COLUMNS)
    upsert_manifest(project_root / "data" / "manifest.csv", records)
    generated_at = now_utc()
    audit = {
        "schema_version": "1.0",
        "audit_metadata": {
            "generated_at": generated_at,
            "article_csv": relative_path(csv_path, project_root),
            "media_csv_files": [relative_path(path, project_root) for path in media_paths],
            "media_csv_count": len(media_paths),
            "media_exclusion_reason": (
                "미디어 CSV는 제목·설명·키워드 단위로 일반 항목 EID/본문 구조와 다르며, "
                "미디어별 공공누리 표시와 제3자 권리 확인이 필요해 본문 수집에서 제외"
            ),
            "sample_size": sample_size,
            "seed": seed,
            "stratification": "분야 문자열의 '/' 앞 대분야; 전 층 최소 1건 + 잔여 비례 배분",
            "sample_allocation": allocation,
            "sampled_eids": [item.eid for item in sample],
            "api_base_url": api_base_url,
            "api_key_present": bool(api_key.strip()),
        },
        "csv_quality": quality,
        "comparison_summary": _summary(records),
        "records": records,
    }
    write_json(project_root / "outputs" / "csv_api_audit.json", audit)
    report_path = project_root / "outputs" / "csv_api_audit_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_render_report(audit), encoding="utf-8")
    return audit


def load_selected_eids(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = {str(name).strip().lower() for name in (reader.fieldnames or [])}
        if "eid" not in fieldnames:
            raise ValueError("선택 파일에는 `eid` 열이 필요합니다.")
        values: list[str] = []
        invalid: list[str] = []
        for row in reader:
            raw = next((value for key, value in row.items() if str(key).strip().lower() == "eid"), "")
            eid = (raw or "").strip().upper()
            if not eid:
                continue
            if not EID_RE.fullmatch(eid):
                invalid.append(eid)
            elif eid not in values:
                values.append(eid)
    if invalid:
        raise ValueError(f"잘못된 EID가 있어 수집을 시작하지 않았습니다: {', '.join(invalid[:10])}")
    return values


def collect_selected(
    *,
    project_root: Path,
    csv_path: Path,
    selected_path: Path,
    api_key: str,
    api_base_url: str = DEFAULT_API_BASE_URL,
    timeout: float = 30.0,
    retries: int = 2,
    client: AksApiClient | None = None,
) -> dict[str, Any]:
    if not api_key.strip():
        raise ValueError("AKS_API_KEY가 설정되지 않아 선택 수집을 시작하지 않았습니다.")
    selected_eids = load_selected_eids(selected_path)
    if not selected_eids:
        return {"selected_count": 0, "success_count": 0, "error_count": 0, "records": []}
    items = load_article_csv(csv_path)
    by_eid = {item.eid: item for item in items if item.eid}
    missing_from_csv = [eid for eid in selected_eids if eid not in by_eid]
    if missing_from_csv:
        raise ValueError(
            "일반 항목 CSV에 없는 EID가 있어 수집을 시작하지 않았습니다: " + ", ".join(missing_from_csv[:10])
        )
    client = client or AksApiClient(api_key, api_base_url, timeout=timeout, retries=retries)
    records = [
        _fetch_record(
            by_eid[eid],
            client=client,
            api_base_url=api_base_url,
            raw_path=project_root / "data" / "raw" / "api" / f"{eid}.json",
            project_root=project_root,
        )
        for eid in selected_eids
    ]
    upsert_manifest(project_root / "data" / "manifest.csv", records)
    return {
        "selected_count": len(selected_eids),
        "success_count": sum(row["status"] in {"ok", "warning"} for row in records),
        "error_count": sum(row["status"] == "api_error" for row in records),
        "records": records,
    }


def _record_from_existing_raw(
    item: CsvItem,
    *,
    raw_path: Path,
    api_base_url: str,
    project_root: Path,
) -> dict[str, Any] | None:
    try:
        raw = raw_path.read_bytes()
        payload = json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    parsed = parse_article(payload)
    eid_match = parsed["eid"] == item.eid
    title_match = normalize_text(parsed["title"]) == normalize_text(item.title)
    status = "ok" if eid_match and title_match and parsed["has_body"] else "warning"
    warnings: list[str] = []
    if not parsed["eid"]:
        warnings.append("api_eid_missing")
    elif not eid_match:
        warnings.append("eid_mismatch")
    if not parsed["title"]:
        warnings.append("api_title_missing")
    elif not title_match:
        warnings.append("title_mismatch")
    if not parsed["has_body"]:
        warnings.append("body_missing")
    collected_at = datetime.fromtimestamp(raw_path.stat().st_mtime, timezone.utc).replace(microsecond=0)
    return _record(
        item,
        parsed=parsed,
        api_url=f"{api_base_url.rstrip('/')}/articles/{item.eid}",
        raw_file_path=relative_path(raw_path, project_root),
        collected_at=collected_at.isoformat().replace("+00:00", "Z"),
        checksum=sha256_bytes(raw),
        status=status,
        error=";".join(warnings),
    )


def collect_all(
    *,
    project_root: Path,
    csv_path: Path,
    api_key: str,
    api_base_url: str = DEFAULT_API_BASE_URL,
    delay_seconds: float = 0.1,
    batch_size: int = 500,
    max_items: int | None = None,
    timeout: float = 30.0,
    retries: int = 2,
    client: AksApiClient | None = None,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """Collect every valid unique CSV EID with restart-safe raw-file skipping.

    This deliberately has no implicit caller in the project; the CLI requires an
    explicit --all flag because it can make tens of thousands of API requests.
    """
    if not api_key.strip():
        raise ValueError("AKS_API_KEY가 설정되지 않아 전체 수집을 시작하지 않았습니다.")
    if delay_seconds < 0:
        raise ValueError("delay_seconds는 0 이상이어야 합니다.")
    if batch_size < 1:
        raise ValueError("batch_size는 1 이상이어야 합니다.")
    all_items = load_article_csv(csv_path)
    unique_by_eid: dict[str, CsvItem] = {}
    for item in all_items:
        if item.eid:
            unique_by_eid.setdefault(item.eid, item)
    items = [unique_by_eid[eid] for eid in sorted(unique_by_eid)]
    if max_items is not None:
        if max_items < 1:
            raise ValueError("max_items는 1 이상이어야 합니다.")
        items = items[:max_items]
    client = client or AksApiClient(api_key, api_base_url, timeout=timeout, retries=retries)
    api_dir = project_root / "data" / "raw" / "api"
    manifest_path = project_root / "data" / "manifest.csv"
    progress_path = project_root / "outputs" / "api_full_collection_progress.json"
    manifest = load_manifest(manifest_path)
    pending_records: list[dict[str, Any]] = []
    counters = {"total": len(items), "processed": 0, "fetched": 0, "skipped_existing": 0, "api_error": 0}

    def flush(*, state: str) -> None:
        if pending_records:
            merge_manifest_records(manifest, pending_records)
            write_manifest(manifest_path, manifest)
            pending_records.clear()
        progress = {
            "updated_at": now_utc(),
            "state": state,
            "csv": relative_path(csv_path, project_root),
            "api_base_url": api_base_url,
            "delay_seconds": delay_seconds,
            **counters,
            "last_eid": last_eid[0],
        }
        write_json(progress_path, progress)
        if progress_callback:
            progress_callback(progress)

    last_eid = [""]
    interrupted = False
    try:
        for item in items:
            last_eid[0] = item.eid or ""
            raw_path = api_dir / f"{item.eid}.json"
            record = _record_from_existing_raw(
                item,
                raw_path=raw_path,
                api_base_url=api_base_url,
                project_root=project_root,
            )
            if record is not None:
                counters["skipped_existing"] += 1
            else:
                record = _fetch_record(
                    item,
                    client=client,
                    api_base_url=api_base_url,
                    raw_path=raw_path,
                    project_root=project_root,
                )
                if record["status"] == "api_error":
                    counters["api_error"] += 1
                else:
                    counters["fetched"] += 1
                if delay_seconds:
                    time.sleep(delay_seconds)
            pending_records.append(record)
            counters["processed"] += 1
            if len(pending_records) >= batch_size:
                flush(state="running")
    except KeyboardInterrupt:
        interrupted = True
    flush(state="interrupted" if interrupted else "complete")
    return {**counters, "interrupted": interrupted, "last_eid": last_eid[0]}


def validate_collection(*, project_root: Path) -> dict[str, Any]:
    """Validate raw API originals and their manifest linkage without changing content."""
    raw_dir = project_root / "data" / "raw" / "api"
    manifest = load_manifest(project_root / "data" / "manifest.csv")
    raw_files = sorted(raw_dir.glob("*.json"), key=lambda path: path.name)
    invalid_json: list[str] = []
    eid_mismatches: list[dict[str, str]] = []
    body_missing: list[str] = []
    checksum_mismatches: list[str] = []
    raw_without_manifest: list[str] = []
    for raw_path in raw_files:
        eid = raw_path.stem.upper()
        row = manifest.get(f"aks:{eid}")
        if row is None:
            raw_without_manifest.append(eid)
        try:
            raw = raw_path.read_bytes()
            payload = json.loads(raw.decode("utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            invalid_json.append(eid)
            continue
        parsed = parse_article(payload)
        if parsed["eid"] != eid:
            eid_mismatches.append({"file_eid": eid, "response_eid": parsed["eid"]})
        if not parsed["has_body"]:
            body_missing.append(eid)
        if row and row.get("checksum") != sha256_bytes(raw):
            checksum_mismatches.append(eid)
    manifest_raw_rows = [
        row
        for row in manifest.values()
        if str(row.get("raw_file_path", "")).startswith("data/raw/api/")
    ]
    manifest_raw_missing = [
        row.get("eid", "")
        for row in manifest_raw_rows
        if not (project_root / str(row.get("raw_file_path"))).is_file()
    ]
    errors = [row for row in manifest.values() if row.get("status") == "api_error"]
    result = {
        "generated_at": now_utc(),
        "scope": "data/raw/api JSON originals and data/manifest.csv linkage",
        "raw_json_count": len(raw_files),
        "valid_json_count": len(raw_files) - len(invalid_json),
        "invalid_json_count": len(invalid_json),
        "response_eid_mismatch_count": len(eid_mismatches),
        "body_missing_count": len(body_missing),
        "checksum_mismatch_count": len(checksum_mismatches),
        "raw_without_manifest_count": len(raw_without_manifest),
        "manifest_raw_missing_count": len(manifest_raw_missing),
        "manifest_api_error_count": len(errors),
        "manifest_api_error_reasons": dict(sorted(Counter(row.get("error", "") for row in errors).items())),
        "examples": {
            "invalid_json_eids": invalid_json[:100],
            "response_eid_mismatches": eid_mismatches[:100],
            "body_missing_eids": body_missing[:100],
            "checksum_mismatch_eids": checksum_mismatches[:100],
            "raw_without_manifest_eids": raw_without_manifest[:100],
            "manifest_raw_missing_eids": manifest_raw_missing[:100],
            "api_error_eids": [row.get("eid", "") for row in errors[:100]],
        },
    }
    write_json(project_root / "outputs" / "api_collection_validation.json", result)
    lines = [
        "# AKS API 원본·manifest 검증 보고서",
        "",
        f"- 실행 시각(UTC): `{result['generated_at']}`",
        f"- 원본 JSON: {result['raw_json_count']:,}건",
        f"- JSON 파싱 성공: {result['valid_json_count']:,}건",
        f"- JSON 파싱 실패: {result['invalid_json_count']:,}건",
        f"- 파일 EID/API 응답 EID 불일치: {result['response_eid_mismatch_count']:,}건",
        f"- 본문 누락: {result['body_missing_count']:,}건",
        f"- SHA-256 불일치: {result['checksum_mismatch_count']:,}건",
        f"- 원본은 있으나 manifest 없음: {result['raw_without_manifest_count']:,}건",
        f"- manifest 원본 경로가 없거나 누락: {result['manifest_raw_missing_count']:,}건",
        f"- API 상세 무응답/오류 manifest 행: {result['manifest_api_error_count']:,}건",
        "",
        "## 판정",
        "",
        "검증에 통과한 JSON은 원본 보관·추적 단위로 다음 담당자에게 전달할 수 있다. "
        "`api_error` 행은 원문이 없어 corpus에서 제외하며, 재시도 시에도 EID와 오류 이력을 유지한다.",
        "",
    ]
    (project_root / "outputs" / "api_collection_validation.md").write_text("\n".join(lines), encoding="utf-8")
    return result
