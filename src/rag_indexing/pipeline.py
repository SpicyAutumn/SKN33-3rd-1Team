from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator


LICENSE_NOTE = (
    "한국학중앙연구원이 저작재산권 전부를 보유한 항목 원고 범위에서 자유이용 가능; "
    "출처 표기 필수. 미디어는 별도 권리 확인 필요."
)
_EID_RE = re.compile(r"^E\d{7}$", re.IGNORECASE)
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_HEADING_RE = re.compile(r"^#{1,6}\s+")
_WHITESPACE_RE = re.compile(r"[ \t\f\v]+")


@dataclass(frozen=True)
class ChunkingConfig:
    """Character-based settings, so runs are reproducible without a tokenizer."""

    max_chars: int = 1_500
    overlap_chars: int = 200
    min_content_chars: int = 20
    require_body: bool = True
    version: str = "v1"

    def __post_init__(self) -> None:
        if self.max_chars < 100:
            raise ValueError("max_chars must be at least 100")
        if not 0 <= self.overlap_chars < self.max_chars:
            raise ValueError("overlap_chars must be non-negative and smaller than max_chars")


@dataclass(frozen=True)
class Chunk:
    """Persisted chunk contract. Retrieval-specific fields are added at query time."""

    chunk_id: str
    document_id: str
    title: str
    content: str
    source_url: str | None
    section: str | None
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_text(value: Any) -> str:
    """Normalize API text while retaining paragraph boundaries and Korean characters."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", html.unescape(str(value)))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _LINK_RE.sub(r"\1", text)
    paragraphs: list[str] = []
    for paragraph in re.split(r"\n\s*\n+", text):
        lines = [_HEADING_RE.sub("", line.strip()) for line in paragraph.split("\n")]
        clean = _WHITESPACE_RE.sub(" ", " ".join(line for line in lines if line)).strip()
        if clean:
            paragraphs.append(clean)
    return "\n\n".join(paragraphs)


def _optional_text(value: Any) -> str | None:
    cleaned = normalize_text(value)
    return cleaned or None


def _aliases(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    aliases = []
    for item in value:
        word = item.get("word") if isinstance(item, dict) else item
        cleaned = _optional_text(word)
        if cleaned:
            aliases.append(cleaned)
    return sorted(set(aliases))


def load_aks_jsonl(path: Path, *, limit: int | None = None) -> Iterator[dict[str, Any]]:
    """Yield records from either AKS JSONL delivery format.

    The first delivery wrapped each API payload as ``{eid, payload, status}``.
    The later raw-data pipeline writes the API payload itself on each line.
    Both forms are accepted so a corpus run remains reproducible regardless of
    which approved Drive handoff the team uses.
    """
    emitted = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if limit is not None and emitted >= limit:
                return
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_number}") from exc
            if not isinstance(record, dict):
                continue
            wrapped_payload = record.get("payload")
            payload = wrapped_payload if isinstance(wrapped_payload, dict) else record
            status = (record.get("status") or payload.get("status")) if isinstance(wrapped_payload, dict) else None
            if status and status != "success":
                continue
            if not isinstance(payload, dict):
                continue
            eid = str(payload.get("eid") or record.get("eid") or "").upper()
            if not _EID_RE.fullmatch(eid):
                continue
            payload = dict(payload)
            payload["eid"] = eid
            emitted += 1
            yield payload


def _split_long_text(text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    """Split one long passage on sentence/word boundaries with deterministic overlap."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            candidates = [text.rfind(marker, start + max_chars // 2, end) for marker in (". ", "? ", "! ", " ")]
            boundary = max(candidates)
            if boundary > start:
                end = boundary + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap_chars, start + 1)
        while start < len(text) and text[start].isspace():
            start += 1
    return chunks


def split_content(text: str, config: ChunkingConfig) -> list[str]:
    """Prefer paragraphs, then split oversized paragraphs without losing text."""
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > config.max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_text(paragraph, max_chars=config.max_chars, overlap_chars=config.overlap_chars))
            continue
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= config.max_chars:
            current = candidate
        else:
            chunks.append(current)
            current = paragraph
    if current:
        chunks.append(current)
    return chunks


def _document_fingerprint(payload: dict[str, Any]) -> str:
    source = {
        "eid": payload["eid"],
        "title": _optional_text(payload.get("headword")) or "",
        "definition": normalize_text(payload.get("definition")),
        "body": normalize_text(payload.get("body")),
    }
    canonical = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def _metadata(payload: dict[str, Any], fingerprint: str, config: ChunkingConfig) -> dict[str, Any]:
    return {
        "eid": payload["eid"],
        "field": _optional_text(payload.get("field")),
        "era": _optional_text(payload.get("era")),
        "primary_type": _optional_text(payload.get("primaryType")),
        "secondary_type": _optional_text(payload.get("secondaryType")),
        "contents_type": _optional_text(payload.get("contentsType")),
        "aliases": _aliases(payload.get("articleAliases")),
        "last_modified_at": _optional_text(payload.get("lastModifiedTime")),
        "license": LICENSE_NOTE,
        "document_fingerprint": fingerprint,
        "chunking_version": config.version,
    }


def build_chunks(payloads: Iterable[dict[str, Any]], config: ChunkingConfig | None = None) -> list[Chunk]:
    """Build deterministic definition/body chunks from AKS API payloads."""
    config = config or ChunkingConfig()
    chunks: list[Chunk] = []
    for payload in payloads:
        eid = str(payload.get("eid") or "").upper()
        if not _EID_RE.fullmatch(eid):
            continue
        title = _optional_text(payload.get("headword")) or eid
        source_url = _optional_text(payload.get("url"))
        body = normalize_text(payload.get("body"))
        if config.require_body and not body:
            continue
        fingerprint = _document_fingerprint({**payload, "eid": eid})
        metadata = _metadata({**payload, "eid": eid}, fingerprint, config)
        for section, content in (("definition", normalize_text(payload.get("definition"))), ("body", body)):
            if len(content) < config.min_content_chars:
                continue
            for ordinal, piece in enumerate(split_content(content, config), start=1):
                chunk_id = f"aks:{eid}:{fingerprint}:{section}:{ordinal:04d}"
                chunks.append(
                    Chunk(
                        chunk_id=chunk_id,
                        document_id=f"aks:{eid}",
                        title=title,
                        content=piece,
                        source_url=source_url,
                        section=section,
                        metadata=dict(metadata),
                    )
                )
    return chunks


def write_chunks_jsonl(path: Path, chunks: Iterable[Chunk]) -> int:
    """Write a portable, line-delimited retrieval corpus without exposing raw media data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1
    return count
