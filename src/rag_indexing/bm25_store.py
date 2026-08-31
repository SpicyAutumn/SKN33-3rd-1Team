from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any, Iterable


_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣ㄱ-ㅎㅏ-ㅣ]+")
# A lightweight query normalizer for common Korean postpositions.  SQLite's
# unicode61 tokenizer does not split ``경복궁에`` into ``경복궁`` and ``에``.
_PARTICLE_SUFFIXES = tuple(
    sorted(
        {
            "으로부터",
            "에서부터",
            "에게서",
            "이라면",
            "이라고",
            "이라는",
            "으로는",
            "에게는",
            "에서는",
            "부터",
            "까지",
            "처럼",
            "보다",
            "만큼",
            "에게",
            "에서",
            "으로",
            "이며",
            "이고",
            "이나",
            "라도",
            "은",
            "는",
            "이",
            "가",
            "을",
            "를",
            "에",
            "의",
            "과",
            "와",
            "도",
            "만",
            "로",
        },
        key=len,
        reverse=True,
    )
)


def tokenize_korean(text: str) -> list[str]:
    """Return safe BM25 query terms while retaining exact Korean nouns.

    This deliberately avoids a heavyweight morphology dependency.  It is a
    first lexical-retrieval baseline: exact title, alias, and content terms
    are indexed by SQLite FTS5, while a small postposition normalization makes
    common questions such as ``경복궁에 대해`` match the title ``경복궁``.
    """

    normalized = unicodedata.normalize("NFC", text).lower()
    terms: list[str] = []
    for raw_token in _TOKEN_RE.findall(normalized):
        terms.append(raw_token)
        for suffix in _PARTICLE_SUFFIXES:
            if raw_token.endswith(suffix) and len(raw_token) > len(suffix) + 1:
                terms.append(raw_token[: -len(suffix)])
                break
    return list(dict.fromkeys(terms))


def _exact_lookup_term(text: str) -> str | None:
    """Normalise a full title/alias for an exact-entity lookup."""

    terms = _TOKEN_RE.findall(unicodedata.normalize("NFC", text).lower())
    return " ".join(terms) or None


def _nullable_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if value and value.upper() != "NONE" else None


def _normalise_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    normalised = {
        key: _nullable_text(value) if isinstance(value, str) else value for key, value in metadata.items()
    }
    aliases = normalised.get("aliases")
    normalised["aliases"] = (
        [alias for alias in (_nullable_text(item) for item in aliases) if alias is not None]
        if isinstance(aliases, list)
        else []
    )
    # The operational corpus is V1 and did not persist this trace value.
    normalised.setdefault("chunking_fingerprint", None)
    return normalised


def _required_text(value: Any, field_name: str) -> str:
    text = _nullable_text(value)
    if text is None:
        raise ValueError(f"BM25 index field {field_name} must be a non-empty string")
    return text


class BM25Retriever:
    """Persistent local BM25 search over the approved AKS chunk JSONL.

    SQLite FTS5 stores the lexical index locally, so it needs no OpenAI call
    and does not modify the shared Pinecone index.  FTS5's ``bm25`` score is
    negated before returning: a larger score always means a stronger lexical
    match in this adapter.
    """

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        if not self.database_path.is_file():
            raise FileNotFoundError(
                f"BM25 index not found: {self.database_path}. Run scripts/build_aks_bm25.py first."
            )

    def search(self, question: str, *, top_k: int = 5) -> list[dict[str, Any]]:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        terms = tokenize_korean(question)
        if not terms:
            return []
        # All generated terms are limited to Korean/Latin letters and digits.
        match_expression = " OR ".join(f"{term}*" for term in terms)
        with sqlite3.connect(self.database_path) as connection:
            exact_rows = connection.execute(
                f"""
                SELECT records.chunk_id, records.document_id, records.title, records.content,
                       records.source_url, records.section, records.metadata_json, 1.0 AS lexical_score
                FROM exact_terms
                JOIN chunk_records AS records ON records.chunk_id = exact_terms.chunk_id
                WHERE exact_terms.term IN ({','.join('?' for _ in terms)})
                GROUP BY records.chunk_id
                ORDER BY MIN(CASE exact_terms.match_kind WHEN 'title' THEN 0 ELSE 1 END),
                         CASE records.section WHEN 'definition' THEN 0 ELSE 1 END,
                         records.chunk_id
                LIMIT ?
                """,
                (*terms, top_k),
            ).fetchall()
            lexical_rows = connection.execute(
                """
                SELECT records.chunk_id, records.document_id, records.title, records.content,
                       records.source_url, records.section, records.metadata_json,
                       -bm25(aks_bm25, 5.0, 3.0, 1.0) AS lexical_score
                FROM aks_bm25
                JOIN chunk_records AS records ON records.rowid = aks_bm25.rowid
                WHERE aks_bm25 MATCH ?
                ORDER BY lexical_score DESC
                LIMIT ?
                """,
                (match_expression, top_k),
            ).fetchall()
        exact_ids = {str(row[0]) for row in exact_rows}
        rows = [*exact_rows, *(row for row in lexical_rows if str(row[0]) not in exact_ids)][:top_k]
        contexts: list[dict[str, Any]] = []
        for rank, row in enumerate(rows, start=1):
            metadata = _normalise_metadata(json.loads(row[6]))
            contexts.append(
                {
                    "chunk_id": str(row[0]),
                    "document_id": _required_text(row[1], "document_id"),
                    "title": _required_text(row[2], "title"),
                    "content": _required_text(row[3], "content"),
                    "source_url": _nullable_text(row[4]),
                    "section": _nullable_text(row[5]),
                    "retrieval_rank": rank,
                    "retrieval_score": float(row[7]),
                    "score_type": "relevance",
                    "metadata": metadata,
                }
            )
        return contexts


def build_bm25_index(
    chunks: Iterable[dict[str, Any]], database_path: Path, *, force: bool = False, batch_size: int = 1_000
) -> int:
    """Build an atomic SQLite FTS5 index from processed AKS chunks.

    ``database_path`` is a generated local artifact.  The final file is only
    replaced after the temporary index has been built successfully.
    """

    target = Path(database_path)
    if target.exists() and not force:
        raise FileExistsError(f"{target} already exists. Pass --force to rebuild it.")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.building")
    if temporary.exists():
        temporary.unlink()

    count = 0
    connection = sqlite3.connect(temporary)
    try:
        connection.execute(
            """
            CREATE TABLE chunk_records (
                chunk_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                title,
                aliases,
                content,
                source_url TEXT NOT NULL,
                section TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE VIRTUAL TABLE aks_bm25 USING fts5(
                title,
                aliases,
                content,
                content='chunk_records',
                content_rowid='rowid',
                tokenize='unicode61'
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE exact_terms (
                term TEXT NOT NULL,
                chunk_id TEXT NOT NULL,
                match_kind TEXT NOT NULL,
                PRIMARY KEY (term, chunk_id, match_kind)
            )
            """
        )
        connection.execute("CREATE INDEX exact_terms_term_index ON exact_terms(term)")
        batch: list[tuple[str, str, str, str, str, str, str, str]] = []
        exact_term_batch: list[tuple[str, str, str]] = []
        for chunk in chunks:
            metadata = chunk.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            aliases = metadata.get("aliases")
            aliases_text = " ".join(str(alias) for alias in aliases) if isinstance(aliases, list) else ""
            values = (
                _required_text(chunk.get("chunk_id"), "chunk_id"),
                _required_text(chunk.get("document_id"), "document_id"),
                _required_text(chunk.get("title"), "title"),
                aliases_text,
                _required_text(chunk.get("content"), "content"),
                _nullable_text(chunk.get("source_url")) or "",
                _nullable_text(chunk.get("section")) or "",
                json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
            )
            batch.append(values)
            title_term = _exact_lookup_term(values[2])
            if title_term:
                exact_term_batch.append((title_term, values[0], "title"))
            if isinstance(aliases, list):
                for alias in aliases:
                    alias_term = _exact_lookup_term(str(alias))
                    if alias_term:
                        exact_term_batch.append((alias_term, values[0], "alias"))
            if len(batch) >= batch_size:
                connection.executemany(
                    "INSERT INTO chunk_records VALUES (?, ?, ?, ?, ?, ?, ?, ?)", batch
                )
                connection.executemany("INSERT OR IGNORE INTO exact_terms VALUES (?, ?, ?)", exact_term_batch)
                count += len(batch)
                batch.clear()
                exact_term_batch.clear()
        if batch:
            connection.executemany("INSERT INTO chunk_records VALUES (?, ?, ?, ?, ?, ?, ?, ?)", batch)
            connection.executemany("INSERT OR IGNORE INTO exact_terms VALUES (?, ?, ?)", exact_term_batch)
            count += len(batch)
        connection.execute(
            "INSERT INTO aks_bm25(rowid, title, aliases, content) "
            "SELECT rowid, title, aliases, content FROM chunk_records"
        )
        connection.execute("CREATE TABLE index_info (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO index_info VALUES ('chunk_count', ?)", (str(count),))
        connection.execute("INSERT INTO aks_bm25(aks_bm25) VALUES ('optimize')")
        connection.commit()
    except Exception:
        connection.close()
        temporary.unlink(missing_ok=True)
        raise
    else:
        connection.close()
        temporary.replace(target)
    return count
