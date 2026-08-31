from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


EID_RE = re.compile(r"^E\d{7}$", re.IGNORECASE)
EID_IN_PATH_RE = re.compile(r"/(?:Contents/Item|Article)/(E\d{7})(?:/|$)", re.IGNORECASE)
ARTICLE_COLUMNS = {"항목명", "분야", "웹사이트 주소"}
MEDIA_COLUMNS = {"제목", "설명", "키워드"}
ATTRIBUTION_TEMPLATE = "[{title}],『한국민족문화대백과사전』"
LICENSE_NOTE = (
    "항목 원고는 한국학중앙연구원이 저작재산권 전부를 보유한 범위에 한해 "
    "공공저작물 자유이용 가능; 출처 표기 필수. 미디어에는 이 조건을 일괄 적용하지 않음."
)


@dataclass(frozen=True)
class CsvItem:
    row_number: int
    title: str
    field: str
    source_url: str
    eid: str | None
    url_error: str = ""

    @property
    def stratum(self) -> str:
        value = self.field.strip()
        return value.split("/", 1)[0] if value else "(분야 누락)"


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    # NFC preserves compatibility jamo such as "ㄱ" while normalizing composed Korean text.
    return " ".join(unicodedata.normalize("NFC", str(value)).split())


def extract_eid(url: str) -> str | None:
    """Extract a canonical EID from an official article URL."""
    value = (url or "").strip()
    if not value:
        return None
    try:
        parsed = urlparse(value)
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.hostname and not parsed.hostname.lower().endswith("aks.ac.kr"):
        return None
    match = EID_IN_PATH_RE.search(parsed.path)
    return match.group(1).upper() if match else None


def classify_url_error(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return "missing_url"
    try:
        parsed = urlparse(value)
    except ValueError:
        return "malformed_url"
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return "malformed_url"
    if parsed.hostname and not parsed.hostname.lower().endswith("aks.ac.kr"):
        return "non_aks_host"
    if not EID_IN_PATH_RE.search(parsed.path):
        return "missing_or_invalid_eid"
    return ""


def inspect_csv_headers(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        return {cell.strip() for cell in next(reader, [])}


def discover_csv_files(raw_dir: Path) -> tuple[Path, list[Path]]:
    article_files: list[Path] = []
    media_files: list[Path] = []
    for path in sorted(raw_dir.glob("*.csv"), key=lambda p: p.name):
        headers = inspect_csv_headers(path)
        if ARTICLE_COLUMNS.issubset(headers):
            article_files.append(path)
        elif MEDIA_COLUMNS.issubset(headers):
            media_files.append(path)
    if len(article_files) != 1:
        names = ", ".join(path.name for path in article_files) or "없음"
        raise ValueError(f"일반 항목 CSV가 정확히 1개여야 합니다(발견: {names}). --csv로 지정하세요.")
    return article_files[0], media_files


def load_article_csv(path: Path) -> list[CsvItem]:
    rows: list[CsvItem] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = {str(name).strip() for name in (reader.fieldnames or [])}
        missing = ARTICLE_COLUMNS - headers
        if missing:
            raise ValueError(f"일반 항목 CSV 필수 열 누락: {', '.join(sorted(missing))}")
        for row_number, row in enumerate(reader, start=2):
            url = (row.get("웹사이트 주소") or "").strip()
            rows.append(
                CsvItem(
                    row_number=row_number,
                    title=(row.get("항목명") or "").strip(),
                    field=(row.get("분야") or "").strip(),
                    source_url=url,
                    eid=extract_eid(url),
                    url_error=classify_url_error(url),
                )
            )
    return rows


def analyze_csv(items: list[CsvItem]) -> dict[str, Any]:
    eid_counts = Counter(item.eid for item in items if item.eid)
    duplicate_eids = {eid: count for eid, count in sorted(eid_counts.items()) if count > 1}
    duplicate_rows = [item for item in items if item.eid and eid_counts[item.eid] > 1]
    missing_titles = [item for item in items if not item.title]
    missing_fields = [item for item in items if not item.field]
    invalid_urls = [item for item in items if item.url_error]

    def examples(rows: Iterable[CsvItem], limit: int = 100) -> list[dict[str, Any]]:
        return [asdict(row) for row in list(rows)[:limit]]

    return {
        "row_count": len(items),
        "valid_eid_rows": sum(1 for item in items if item.eid),
        "unique_eid_count": len(eid_counts),
        "duplicate_eid_count": len(duplicate_eids),
        "duplicate_row_count": len(duplicate_rows),
        "missing_title_count": len(missing_titles),
        "missing_field_count": len(missing_fields),
        "invalid_url_count": len(invalid_urls),
        "url_error_counts": dict(sorted(Counter(item.url_error for item in invalid_urls).items())),
        "field_counts": dict(sorted(Counter(item.field or "(분야 누락)" for item in items).items())),
        "stratum_counts": dict(sorted(Counter(item.stratum for item in items).items())),
        "duplicate_eids": duplicate_eids,
        "examples": {
            "duplicate_rows": examples(duplicate_rows),
            "missing_titles": examples(missing_titles),
            "missing_fields": examples(missing_fields),
            "invalid_urls": examples(invalid_urls),
        },
    }


def _allocation(group_sizes: dict[str, int], sample_size: int) -> dict[str, int]:
    strata = sorted(group_sizes)
    if sample_size < len(strata):
        raise ValueError(
            f"표본 크기({sample_size})가 유효 대분야 수({len(strata)})보다 작아 모든 층을 포함할 수 없습니다."
        )
    allocation = {name: 1 for name in strata}
    remaining = sample_size - len(strata)
    total = sum(group_sizes.values())
    quotas = {name: remaining * group_sizes[name] / total for name in strata}
    for name in strata:
        allocation[name] += int(quotas[name])
    assigned = sum(allocation.values())
    ranked = sorted(strata, key=lambda name: (-(quotas[name] % 1), name))
    for name in ranked[: sample_size - assigned]:
        allocation[name] += 1
    return allocation


def stratified_sample(items: list[CsvItem], sample_size: int, seed: int) -> tuple[list[CsvItem], dict[str, int]]:
    """Sample valid unique EIDs, covering every top-level CSV field stratum."""
    unique_by_eid: dict[str, CsvItem] = {}
    for item in items:
        if item.eid and item.title and item.field:
            unique_by_eid.setdefault(item.eid, item)
    groups: dict[str, list[CsvItem]] = defaultdict(list)
    for item in unique_by_eid.values():
        groups[item.stratum].append(item)
    if sample_size > len(unique_by_eid):
        raise ValueError("표본 크기가 유효 고유 EID 수보다 큽니다.")
    allocation = _allocation({name: len(rows) for name, rows in groups.items()}, sample_size)
    selected: list[CsvItem] = []
    for name in sorted(groups):
        rows = sorted(groups[name], key=lambda item: (item.eid or "", item.row_number))
        derived_seed = int(hashlib.sha256(f"{seed}:{name}".encode("utf-8")).hexdigest(), 16)
        random.Random(derived_seed).shuffle(rows)
        selected.extend(rows[: allocation[name]])
    return sorted(selected, key=lambda item: (item.stratum, item.eid or "")), allocation


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def write_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    # Windows can briefly lock a file while an editor, antivirus scanner, or
    # another reader releases its handle. Retrying preserves atomic replacement
    # without leaving a partially written manifest visible to other workers.
    last_error: PermissionError | None = None
    for attempt in range(10):
        try:
            temporary.replace(path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.2 * (attempt + 1))
    if last_error:
        raise last_error


def write_json(path: Path, value: Any) -> None:
    content = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    write_bytes_atomic(path, content)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)
