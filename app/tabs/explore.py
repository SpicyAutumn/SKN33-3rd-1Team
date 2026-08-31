"""이번 검색 결과로 연관 문화유산 지도를 만든다.

검색 결과에는 분야·시대·유형·이칭 메타데이터가 함께 들어온다. 그 값이 겹치는
항목을 이어 붙이면 추가 검색 없이 "왜 연결됐는지" 설명 가능한 지도가 만들어진다.
표시 형식(`exploration_map.html`)은 그대로 두고 데이터만 실제 값으로 채운다.
"""

import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

import regions


# 메타데이터에서 가지로 쓸 축. 값의 앞부분(대분류)까지만 비교해 너무 잘게 쪼개지지 않게 한다.
AXES = (
    ("field", "분야", 2),
    ("era", "시대", 1),
    ("primary_type", "유형", 1),
)

SUMMARY_LIMIT = 160


def _particle(word: str, with_final: str, without_final: str) -> str:
    """받침 유무에 따라 조사를 고른다. 한글이 아니면 받침 없는 쪽을 쓴다."""
    last = word.strip()[-1:] if word.strip() else ""
    if not ("가" <= last <= "힣"):
        return without_final
    return with_final if (ord(last) - 0xAC00) % 28 else without_final


def _text(value) -> str:
    text = str(value or "").strip()
    return "" if text.upper() == "NONE" else text


def _region(context: dict) -> tuple[str, str] | None:
    """지역은 메타데이터에 없으므로 제목과 본문에서 뽑는다."""
    return regions.detect(_text(context.get("title")), _text(context.get("content")))


def _values(context: dict, key: str, depth: int) -> set[str]:
    """`예술·체육/조각 | 종교·철학/불교`처럼 여러 값을 가진 필드를 갈라 낸다."""
    raw = _text(context.get("metadata", {}).get(key))
    if not raw:
        return set()
    values = set()
    for part in raw.split("|"):
        segments = [s for s in part.strip().split("/") if s]
        if segments:
            values.add("/".join(segments[:depth]))
    return values


def _unique_documents(contexts: list[dict]) -> list[dict]:
    """같은 문서의 여러 조각 중 순위가 앞선 하나만 남긴다."""
    seen: dict[str, dict] = {}
    for context in contexts:
        key = context.get("document_id") or context.get("title") or ""
        if key and key not in seen:
            seen[key] = context
    return list(seen.values())


def _summary(context: dict) -> str:
    content = _text(context.get("content"))
    if not content:
        return "이번 검색 결과에 본문이 없습니다."
    return content[:SUMMARY_LIMIT] + ("…" if len(content) > SUMMARY_LIMIT else "")


def _build_payload(question: str, contexts: list[dict]) -> dict | None:
    documents = _unique_documents(contexts)
    if not documents:
        return None

    root = documents[0]
    root_title = _text(root.get("title")) or "검색 결과"
    others = [d for d in documents[1:] if _text(d.get("title")) and _text(d.get("title")) != root_title]

    keywords: list[dict] = []
    related: dict[str, list[dict]] = {}
    summaries: dict[str, str] = {root_title: _summary(root)}

    linked: set[str] = set()
    for key, label, depth in AXES:
        root_values = _values(root, key, depth)
        if not root_values:
            continue
        for value in sorted(root_values):
            peers = [d for d in others if value in _values(d, key, depth)]
            if not peers:
                continue
            josa_wa = _particle(root_title, "과", "와")
            josa_ga = _particle(label, "이", "가")
            node = f"{label} : {value}"
            keywords.append(
                {"keyword": node, "relation": f"{root_title}{josa_wa} {label}{josa_ga} 같습니다"}
            )
            related[node] = []
            for peer in peers:
                title = _text(peer.get("title"))
                linked.add(title)
                summaries.setdefault(title, _summary(peer))
                related[node].append({"keyword": title, "relation": f"{label} {value}"})
            summaries[node] = (
                f"이번 검색에서 {label}{josa_ga} `{value}`인 항목 {len(peers)}건이 함께 나왔습니다."
            )

    root_region = _region(root)
    if root_region:
        place, basis = root_region
        peers = [d for d in others if (_region(d) or ("", ""))[0] == place]
        josa_wa = _particle(root_title, "과", "와")
        node = f"지역 : {place}"
        keywords.append({"keyword": node, "relation": f"{root_title}{josa_wa} 지역이 같습니다"})
        summaries[node] = (
            f"`{place}` 지역입니다. {basis}에서 확인했습니다."
            + (f" 이번 검색에서 같은 지역 항목 {len(peers)}건이 함께 나왔습니다." if peers else "")
        )
        if peers:
            related[node] = []
            for peer in peers:
                title = _text(peer.get("title"))
                linked.add(title)
                summaries.setdefault(title, _summary(peer))
                related[node].append({"keyword": title, "relation": f"{place} 지역"})

    # 축에 걸리지 않은 항목도 검색 결과이므로 뿌리에 직접 붙인다.
    for peer in others:
        title = _text(peer.get("title"))
        if title in linked:
            continue
        rank = peer.get("retrieval_rank")
        keywords.append({"keyword": title, "relation": f"같은 검색에서 {rank}위로 나왔습니다"})
        summaries.setdefault(title, _summary(peer))

    for alias in _aliases(root):
        if alias != root_title:
            node = f"이칭 : {alias}"
            keywords.append({"keyword": node, "relation": "같은 유산을 부르는 다른 이름"})
            summaries.setdefault(node, f"`{root_title}`의 이칭입니다.")

    if not keywords:
        return None
    return {"question": question, "root": root_title, "keywords": keywords, "related": related, "summaries": summaries}


def _aliases(context: dict) -> list[str]:
    raw = context.get("metadata", {}).get("aliases")
    if isinstance(raw, list):
        return [_text(item) for item in raw if _text(item)]
    return [part.strip() for part in _text(raw).split(",") if part.strip()]


def render() -> None:
    st.subheader("문화유산 탐험 지도")
    st.caption("이번 검색에서 함께 나온 문화유산을 분야·시대·유형으로 이어 붙였습니다. 눌러서 펼쳐 보세요.")

    result = st.session_state.get("last_result")
    if not result:
        st.info("질문하기 탭에서 답변을 받은 뒤 탐험 지도를 확인해 주세요.")
        return

    payload = _build_payload(result.get("question", ""), result.get("retrieved_contexts", []))
    if payload is None:
        st.info("이번 응답에는 이어 볼 만한 문화유산이 없습니다. 다른 질문을 해 보세요.")
        return

    template = (Path(__file__).resolve().parents[1] / "components" / "exploration_map.html").read_text(encoding="utf-8")
    # 검색된 본문이 그대로 들어가므로 스크립트를 끊지 못하도록 막는다.
    encoded = (
        json.dumps(payload, ensure_ascii=False)
        .replace("<", "\u003c")
        .replace(">", "\u003e")
        .replace("&", "\u0026")
    )
    components.html(template.replace("__EXPLORATION_DATA__", encoded), height=660, scrolling=False)
    st.caption(
        f"이번 검색 결과 {len(payload['keywords'])}개 가지로 만들었습니다. "
        "연결 근거는 한국민족문화대백과사전의 분야·시대·유형 정보입니다."
    )
