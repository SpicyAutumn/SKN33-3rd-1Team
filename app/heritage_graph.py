"""탐험 지도의 데이터 계층.

이번 질문의 검색 결과만으로는 지도를 그릴 수 없다. `top_k`가 3이라 이어 붙일
항목이 많아야 둘이다. 75,835건 가운데 3건만 보고 지도를 그리는 셈이었다.

그래서 원천을 둘로 나눈다.

1. `data/manifest.csv` — 전체 75,835건의 제목·분야·유형·시대·출처.
   저장소에 있으므로 호출 비용이 없다. 축 값과 후보 풀을 여기서 얻는다.
2. Pinecone 메타데이터 필터 검색 — 후보가 수백 건일 때 무엇을 보여줄지 고른다.
   축 조건을 걸고 뜻이 가까운 순으로 뽑는다.

축마다 "왜 연결됐는지"를 함께 돌려준다. 이유를 못 대는 연결은 넣지 않는다.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Iterable

import rag_client
import regions

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "data" / "manifest.csv"

# 한 축에 보여 줄 최대 개수. 너무 많으면 로드맵이 아니라 목록이 된다.
AXIS_LIMIT = 5

# 대분류만 맞춰 후보를 넓힌다. `조선/조선 전기`와 `조선/조선 후기`는 사용자에게
# 모두 "조선"이다. 값이 정확히 같은 것만 묶으면 연결이 지나치게 끊긴다.
_VALUE_SEPARATOR = "|"
_LEVEL_SEPARATOR = "/"


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.upper() == "NONE" else text


def top_level(value: str) -> str:
    """`조선/조선 전기 | 조선/조선 후기` -> `조선`."""
    first = _clean(value).split(_VALUE_SEPARATOR)[0]
    return first.split(_LEVEL_SEPARATOR)[0].strip()


class Entry:
    """만든 목록의 문화유산 한 건."""

    __slots__ = ("document_id", "eid", "title", "field", "item_type", "period", "source_url")

    def __init__(self, row: dict[str, str]) -> None:
        self.document_id = _clean(row.get("document_id"))
        self.eid = _clean(row.get("eid"))
        self.title = _clean(row.get("api_title"))
        self.field = _clean(row.get("api_field"))
        self.item_type = _clean(row.get("item_type"))
        self.period = _clean(row.get("period"))
        self.source_url = _clean(row.get("source_url"))

    @property
    def region(self) -> str:
        return regions.from_title(self.title) or ""

    def summary_fields(self) -> list[tuple[str, str]]:
        pairs = [("시대", self.period), ("분야", self.field), ("유형", self.item_type)]
        if self.region:
            pairs.append(("지역", self.region))
        return [(label, value) for label, value in pairs if value]


def _read_manifest(path: Path) -> list[Entry]:
    with io.open(path, encoding="utf-8-sig", newline="") as handle:
        return [Entry(row) for row in csv.DictReader(handle)]


class Catalog:
    """만든 목록 전체를 제목·문서 id로 찾을 수 있게 담아 둔다."""

    def __init__(self, entries: list[Entry]) -> None:
        self.entries = [e for e in entries if e.document_id and e.title]
        self.by_document: dict[str, Entry] = {e.document_id: e for e in self.entries}
        self.by_title: dict[str, Entry] = {}
        for entry in self.entries:
            # 같은 제목이 여럿이면 먼저 나온 것을 쓴다. 목록 순서가 곧 수집 순서다.
            self.by_title.setdefault(entry.title, entry)

    def find(self, key: str) -> Entry | None:
        key = _clean(key)
        if not key:
            return None
        return self.by_document.get(key) or self.by_title.get(key)

    def resolve(self, contexts: Iterable[dict[str, Any]]) -> Entry | None:
        """검색 결과에서 지도의 뿌리로 삼을 문서를 고른다. 앞선 순위부터 본다."""
        for context in contexts:
            entry = self.find(_clean(context.get("document_id"))) or self.find(
                _clean(context.get("title"))
            )
            if entry:
                return entry
        return None

    def values_sharing_top_level(self, column: str, value: str) -> list[str]:
        """같은 대분류에 속한 원본 문자열 목록. Pinecone `$in` 필터에 쓴다."""
        wanted = top_level(value)
        if not wanted:
            return []
        found = {
            getattr(entry, column)
            for entry in self.entries
            if getattr(entry, column) and top_level(getattr(entry, column)) == wanted
        }
        return sorted(found)

    def titles_starting_with(self, prefix: str) -> list[Entry]:
        """`경복궁 경회루`처럼 뿌리 이름으로 시작하는 항목. 구성 요소에 해당한다."""
        prefix = _clean(prefix)
        if len(prefix) < 2:
            return []
        return [
            entry
            for entry in self.entries
            if entry.title != prefix and entry.title.startswith(prefix)
        ]

    def in_region(self, place: str) -> list[Entry]:
        place = _clean(place)
        if not place:
            return []
        return [entry for entry in self.entries if entry.region == place]


_catalog: Catalog | None = None


def catalog() -> Catalog:
    """만든 목록을 한 번만 읽는다. 7만 행이라 매번 읽으면 화면이 느려진다."""
    global _catalog
    if _catalog is None:
        _catalog = Catalog(_read_manifest(MANIFEST_PATH))
    return _catalog


class Neighbors:
    """Pinecone 메타데이터 필터 검색.

    `PineconeRetriever`는 필터를 받는 공개 메서드가 없어 색인 객체를 직접 쓴다.
    검색 담당 쪽에 필터를 받는 `search()`가 생기면 이 클래스는 그것을 쓰면 된다.
    """

    def __init__(self, retriever: Any) -> None:
        self._retriever = retriever
        self._anchors: dict[str, str | None] = {}

    def anchor(self, document_id: str) -> str | None:
        """뿌리 문서를 대표할 청크 id.

        제목만 임베딩해서 이웃을 찾으면 `경복궁`이 `계궁`·`양궁`처럼 짧은
        낱말과 붙는다. 글자가 비슷할 뿐 뜻은 멀다. 이미 색인된 그 문서의
        벡터를 그대로 쓰면 문서 대 문서로 비교하게 되어 훨씬 정확하다.
        정의 문단을 먼저 쓰고, 없으면 아무 청크나 쓴다.
        """
        if document_id in self._anchors:
            return self._anchors[document_id]
        response = self._retriever._index.query(
            vector=[0.0] * 1536,
            top_k=10,
            include_metadata=True,
            namespace=self._retriever.namespace,
            filter={"document_id": {"$eq": document_id}},
        )
        matches = response.get("matches", [])
        chosen = next(
            (m["id"] for m in matches if (m.get("metadata") or {}).get("section") == "definition"),
            matches[0]["id"] if matches else None,
        )
        self._anchors[document_id] = chosen
        return chosen

    def search(
        self,
        anchor_id: str,
        *,
        limit: int,
        metadata_filter: dict[str, Any] | None = None,
        exclude_documents: set[str] | None = None,
    ) -> list[tuple[str, float]]:
        """`(document_id, 유사도)` 목록. 같은 문서의 여러 청크는 최고 점수만 남긴다."""
        excluded = exclude_documents or set()
        # 같은 문서의 청크가 여러 개 올라오므로 넉넉히 받아서 문서 단위로 접는다.
        response = self._retriever._index.query(
            id=anchor_id,
            top_k=max(limit * 8, 40),
            include_metadata=True,
            namespace=self._retriever.namespace,
            filter=metadata_filter or None,
        )
        best: dict[str, float] = {}
        for match in response.get("matches", []):
            metadata = match.get("metadata") or {}
            document_id = _clean(metadata.get("document_id"))
            if not document_id or document_id in excluded:
                continue
            score = float(match.get("score") or 0.0)
            if score > best.get(document_id, -1.0):
                best[document_id] = score
        ranked = sorted(best.items(), key=lambda item: (-item[1], item[0]))
        return ranked[:limit]


def build_neighbors() -> Neighbors | None:
    """검색 연결이 없으면 `None`. 그때는 만든 목록만으로 지도를 그린다."""
    if rag_client.missing_env():
        return None
    from rag_indexing.pinecone_store import PineconeRetriever

    return Neighbors(PineconeRetriever())


def _node(entry: Entry, reason: str) -> dict[str, Any]:
    return {
        "document_id": entry.document_id,
        "title": entry.title,
        "reason": reason,
        "period": entry.period,
        "field": entry.field,
        "item_type": entry.item_type,
        "region": entry.region,
        "source_url": entry.source_url,
    }


def build_map(
    root_key: str,
    *,
    neighbors: Neighbors | None = None,
    limit: int = AXIS_LIMIT,
) -> dict[str, Any] | None:
    """한 문화유산을 뿌리로 연관 항목 지도를 만든다.

    축마다 이미 나온 항목은 다시 넣지 않는다. 같은 항목이 여러 가지에 매달리면
    로드맵이 아니라 그물이 되어 어디로 갈지 고르기 어려워진다.
    """
    book = catalog()
    root = book.find(root_key)
    if root is None:
        return None

    used: set[str] = {root.document_id}
    # 같은 제목의 문서가 여럿 있다. `경주`나 `훈민정음`처럼 이름이 겹치면
    # 한 가지에 같은 이름이 세 번 걸려 로드맵이 읽히지 않는다.
    seen_titles: set[str] = {root.title}
    branches: list[dict[str, Any]] = []

    def add(title: str, note: str, nodes: list[dict[str, Any]]) -> None:
        fresh: list[dict[str, Any]] = []
        for node in nodes:
            if node["document_id"] in used or node["title"] in seen_titles:
                continue
            used.add(node["document_id"])
            seen_titles.add(node["title"])
            fresh.append(node)
            if len(fresh) >= limit:
                break
        if fresh:
            branches.append({"title": title, "note": note, "nodes": fresh})

    anchor = neighbors.anchor(root.document_id) if neighbors is not None else None

    # 1. 구성 요소 — 만든 목록만으로 확실하게 판별된다.
    parts = book.titles_starting_with(root.title)
    if parts:
        ordered = sorted(parts, key=lambda e: e.title)
        if anchor:
            # 가나다순으로 두면 `경복궁 강녕전`이 앞서고 정작 정전인 `근정전`이
            # 밀린다. 뿌리 문서와 가까운 순으로 다시 세운다.
            by_id = {e.document_id: e for e in parts}
            ranked = neighbors.search(
                anchor,
                limit=limit,
                metadata_filter={"document_id": {"$in": sorted(by_id)}},
            )
            ordered = [by_id[d] for d, _ in ranked if d in by_id] or ordered
        add(
            "이 안에 있는 것",
            f"이름이 `{root.title}`으로 시작하는 항목입니다.",
            [_node(e, f"{root.title}의 일부") for e in ordered],
        )
        # 보여 주지 못한 구성 요소도 다른 가지에 다시 넣지 않는다. 그러지 않으면
        # `같은 시대`가 온통 `경복궁 ○○`으로 채워져 다른 유산으로 갈 길이 막힌다.
        used.update(e.document_id for e in parts)
        seen_titles.update(e.title for e in parts)

    if anchor:
        # 2. 같은 시대 — 대분류가 같은 원본 문자열을 모두 건다.
        era_values = book.values_sharing_top_level("period", root.period)
        if era_values:
            era = top_level(root.period)
            found = neighbors.search(
                anchor,
                limit=limit,
                metadata_filter={"era": {"$in": era_values}},
                exclude_documents=used,
            )
            add(
                f"같은 시대 · {era}",
                f"`{era}`에 속한 항목 가운데 뜻이 가까운 순입니다.",
                [
                    _node(book.by_document[d], f"{era} 시대")
                    for d, _ in found
                    if d in book.by_document
                ],
            )

        # 3. 같은 유형 — 궁궐이면 궁궐, 탑이면 탑.
        type_values = book.values_sharing_top_level("item_type", root.item_type)
        if type_values:
            kind = top_level(root.item_type)
            found = neighbors.search(
                anchor,
                limit=limit,
                metadata_filter={"primary_type": {"$in": type_values}},
                exclude_documents=used,
            )
            add(
                f"같은 유형 · {kind}",
                f"`{kind}`으로 분류된 항목입니다.",
                [
                    _node(book.by_document[d], f"{kind} 유형")
                    for d, _ in found
                    if d in book.by_document
                ],
            )

    # 4. 같은 지역 — 제목 앞머리로 판별한다. 좌표가 없어 이 방법뿐이다.
    if root.region:
        # 지역 이름 자체가 제목인 문서(`경주`)는 문화유산이 아니라 지역 설명이다.
        nearby = [
            e
            for e in book.in_region(root.region)
            if e.document_id not in used and e.title != root.region
        ]
        # 지역은 Pinecone 메타데이터에 없어 뜻으로 순위를 매길 수 없다. 가나다순으로
        # 두면 `강릉 갈골과줄`처럼 결이 다른 항목이 앞에 온다. 유형과 분야가 같은
        # 것을 먼저 보여 주면 적어도 성격이 비슷한 이웃이 앞에 선다.
        def affinity(entry: Entry) -> tuple[int, int, str]:
            same_type = top_level(entry.item_type) == top_level(root.item_type)
            same_field = top_level(entry.field) == top_level(root.field)
            return (0 if same_type else 1, 0 if same_field else 1, entry.title)

        add(
            f"같은 지역 · {root.region}",
            f"이름 앞머리가 `{root.region}`인 항목입니다.",
            [_node(e, f"{root.region} 소재") for e in sorted(nearby, key=affinity)],
        )

    # 5. 몰랐던 연결 — 유형을 일부러 뒤집는다.
    # 앞의 축들이 같은 유형에서 가까운 것을 이미 가져갔으므로, 그냥 두면
    # 여기도 궁궐 옆의 궁궐이 나온다. 유적을 빼야 인물·사건·개념이 올라온다.
    if anchor:
        other_types = book.values_sharing_top_level("item_type", root.item_type)
        found = neighbors.search(
            anchor,
            limit=limit,
            metadata_filter={"primary_type": {"$nin": other_types}} if other_types else None,
            exclude_documents=used,
        )
        add(
            "뜻밖의 이웃",
            f"`{top_level(root.item_type) or '같은 유형'}`이 아닌 항목 가운데 내용이 가까운 것입니다.",
            [
                _node(book.by_document[d], "내용이 가깝습니다")
                for d, _ in found
                if d in book.by_document
            ],
        )

    return {
        "root": {
            "document_id": root.document_id,
            "title": root.title,
            "fields": root.summary_fields(),
            "source_url": root.source_url,
        },
        "branches": branches,
    }
