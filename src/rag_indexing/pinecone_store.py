from __future__ import annotations

import os
import re
import time
from dataclasses import asdict
from typing import Any, Callable, Iterable

from .pipeline import Chunk

EMBEDDING_INPUT_VERSION = "v2-title-section-era-primary-type-aliases-content"


def embedding_text(chunk: Chunk) -> str:
    """Build the team-selected text that is sent to the embedding model."""
    section_labels = {"definition": "정의", "body": "상세 본문"}
    lines = [
        f"제목: {chunk.title}",
        f"구역: {section_labels.get(chunk.section or '', chunk.section or '미상')}",
    ]
    if era := chunk.metadata.get("era"):
        lines.append(f"시대: {era}")
    if primary_type := chunk.metadata.get("primary_type"):
        lines.append(f"유형: {primary_type}")
    aliases = chunk.metadata.get("aliases")
    if isinstance(aliases, list) and aliases:
        lines.append(f"이칭: {', '.join(str(alias) for alias in aliases)}")
    lines.append(f"본문: {chunk.content}")
    return "\n".join(lines)


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value or value.startswith("{{"):
        raise RuntimeError(f"{name} must be set in .env before indexing or searching.")
    return value


def _flat_metadata(chunk: Chunk) -> dict[str, Any]:
    """Pinecone metadata must be scalar/list values; retain enough data for citations."""
    values = {
        "document_id": chunk.document_id,
        "title": chunk.title,
        "content": chunk.content,
        "source": chunk.source_url or "",
        "section": chunk.section or "",
        "embedding_input_version": EMBEDDING_INPUT_VERSION,
        **chunk.metadata,
    }
    return {key: value for key, value in values.items() if value is not None}


class PineconeRetriever:
    """Small adapter that returns the team's RetrievedContext contract."""

    def __init__(
        self, *, index_name: str | None = None, embedding_model: str | None = None, namespace: str | None = None
    ) -> None:
        self.index_name = index_name or _require_env("PINECONE_INDEX_NAME")
        self.embedding_model = embedding_model or os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        self.namespace = namespace if namespace is not None else os.getenv("PINECONE_NAMESPACE", "")
        try:
            from openai import OpenAI
            from pinecone import Pinecone
        except ImportError as exc:
            raise RuntimeError("Install requirements.txt before using PineconeRetriever.") from exc
        self._openai = OpenAI(api_key=_require_env("OPENAI_API_KEY"))
        self._index = Pinecone(api_key=_require_env("PINECONE_API_KEY")).Index(self.index_name)

    def _embed(self, texts: list[str], *, max_retries: int = 12) -> list[list[float]]:
        """Embed one batch, waiting for the API when its per-minute limit is reached."""
        from openai import RateLimitError

        for attempt in range(max_retries + 1):
            try:
                response = self._openai.embeddings.create(model=self.embedding_model, input=texts)
                return [item.embedding for item in response.data]
            except RateLimitError as exc:
                if attempt >= max_retries:
                    raise
                # The API error normally gives an exact cooldown such as "try again in 4.6s".
                match = re.search(r"try again in ([0-9.]+)s", str(exc), flags=re.IGNORECASE)
                wait_seconds = max(5.0, float(match.group(1)) + 1.0) if match else min(60.0, 2.0**attempt)
                print(f"OpenAI 분당 한도 도달: {wait_seconds:.1f}초 대기 후 재시도합니다.", flush=True)
                time.sleep(wait_seconds)
        raise RuntimeError("Unreachable retry state")

    def _current_embedding_ids(self, chunks: list[Chunk]) -> set[str]:
        """Return IDs only when both embedding and chunking formats match the current chunk."""
        expected_by_id = {
            chunk.chunk_id: (
                chunk.metadata.get("chunking_version"),
                chunk.metadata.get("chunking_fingerprint"),
            )
            for chunk in chunks
        }
        response = self._index.fetch(ids=list(expected_by_id), namespace=self.namespace)
        vectors = getattr(response, "vectors", None)
        if vectors is None and isinstance(response, dict):
            vectors = response.get("vectors", {})
        if not isinstance(vectors, dict):
            return set()
        ready: set[str] = set()
        for chunk_id, vector in vectors.items():
            metadata = getattr(vector, "metadata", None)
            if metadata is None and isinstance(vector, dict):
                metadata = vector.get("metadata", {})
            expected_chunking = expected_by_id.get(str(chunk_id))
            if (
                isinstance(metadata, dict)
                and expected_chunking is not None
                and metadata.get("embedding_input_version") == EMBEDDING_INPUT_VERSION
                and metadata.get("chunking_version") == expected_chunking[0]
                and metadata.get("chunking_fingerprint") == expected_chunking[1]
            ):
                ready.add(str(chunk_id))
        return ready

    def upsert(
        self,
        chunks: Iterable[Chunk],
        *,
        batch_size: int = 64,
        resume: bool = True,
        progress_callback: Callable[[int], None] | None = None,
    ) -> dict[str, int]:
        batch = list(chunks)
        uploaded = 0
        skipped = 0
        for start in range(0, len(batch), batch_size):
            current = batch[start : start + batch_size]
            if resume:
                already_current = self._current_embedding_ids(current)
                skipped += len(already_current)
                current = [chunk for chunk in current if chunk.chunk_id not in already_current]
            if not current:
                if progress_callback:
                    progress_callback(min(start + batch_size, len(batch)))
                continue
            vectors = self._embed([embedding_text(chunk) for chunk in current])
            self._index.upsert(
                vectors=[
                    {"id": chunk.chunk_id, "values": vector, "metadata": _flat_metadata(chunk)}
                    for chunk, vector in zip(current, vectors, strict=True)
                ],
                namespace=self.namespace,
            )
            uploaded += len(current)
            if progress_callback:
                progress_callback(min(start + batch_size, len(batch)))
            if start == 0 or (start // batch_size + 1) % 10 == 0:
                print(
                    f"진행: {min(start + batch_size, len(batch)):,}/{len(batch):,} "
                    f"(이번 실행 업로드 {uploaded:,}, 건너뜀 {skipped:,})",
                    flush=True,
                )
        return {"uploaded": uploaded, "skipped_current": skipped, "total": len(batch)}

    def search(self, question: str, *, top_k: int = 5) -> list[dict[str, Any]]:
        vector = self._embed([question])[0]
        response = self._index.query(vector=vector, top_k=top_k, include_metadata=True, namespace=self.namespace)
        matches = getattr(response, "matches", None)
        if matches is None and isinstance(response, dict):
            matches = response.get("matches", [])
        contexts: list[dict[str, Any]] = []
        for rank, match in enumerate(matches or [], start=1):
            metadata = getattr(match, "metadata", None)
            if metadata is None and isinstance(match, dict):
                metadata = match.get("metadata", {})
            metadata = dict(metadata or {})
            score = getattr(match, "score", None)
            if score is None and isinstance(match, dict):
                score = match.get("score")
            chunk_id = getattr(match, "id", None)
            if chunk_id is None and isinstance(match, dict):
                chunk_id = match.get("id")
            # The current Track B contract calls this field `source`. Existing
            # vectors used `source_url`, so accept both while returning one
            # stable, strict-schema-friendly shape to generation code.
            source = metadata.pop("source", None) or metadata.pop("source_url", None) or None
            contexts.append(
                {
                    "chunk_id": str(chunk_id),
                    "document_id": str(metadata.pop("document_id", "")),
                    "title": str(metadata.pop("title", "")),
                    "content": str(metadata.pop("content", "")),
                    "source": source,
                    "page": metadata.pop("page", None),
                    "section": metadata.pop("section", None) or None,
                    "retrieval_rank": rank,
                    "retrieval_score": float(score) if score is not None else None,
                    "score_type": "similarity" if score is not None else "unknown",
                    "metadata": metadata,
                }
            )
        return contexts
