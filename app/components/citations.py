"""Citation and evidence rendering components."""

import streamlit as st

from mock_responses import SOURCE_NAME


def group_by_document(citations: list[dict]) -> list[dict]:
    """같은 문서의 Citation을 하나로 묶는다.

    검색은 청크 단위라 한 문서에서 여러 청크가 올라올 수 있다. 그대로 나열하면
    같은 제목이 반복되므로 `document_id` 기준으로 묶어 한 번만 보여 준다.
    문서 순서와 문서 안 근거 순서는 모두 `retrieval_rank`가 빠른 쪽이 먼저다.
    """
    groups: dict[str, dict] = {}
    for item in citations:
        # document_id가 없으면 청크를 각각 독립 문서로 취급해 병합 사고를 막는다.
        key = item.get("document_id") or item.get("chunk_id") or item.get("title") or ""
        group = groups.setdefault(
            key,
            {
                "title": item.get("title") or "제목 없는 자료",
                "source_url": item.get("source_url"),
                "items": [],
            },
        )
        if not group["source_url"]:
            group["source_url"] = item.get("source_url")
        group["items"].append(item)

    def rank(item: dict) -> int:
        value = item.get("retrieval_rank")
        return value if isinstance(value, int) else 10**6

    ordered = []
    for group in groups.values():
        group["items"].sort(key=rank)
        ordered.append(group)
    ordered.sort(key=lambda group: rank(group["items"][0]))
    return ordered


def render(citations: list[dict]) -> None:
    if not citations:
        return

    st.subheader("출처와 근거")
    for index, group in enumerate(group_by_document(citations), start=1):
        items = group["items"]
        sections = [item["section"] for item in items if item.get("section")]

        with st.container(border=True):
            st.markdown(f"**{index}. {group['title']}**")
            details = f"{SOURCE_NAME} · {', '.join(sections)}" if sections else SOURCE_NAME
            st.caption(details)
            if group["source_url"]:
                st.link_button("공식 원문 보기 ↗", group["source_url"], key=f"source-{index}")

            contents = [item for item in items if item.get("content")]
            if not contents:
                continue
            label = "근거 문장 보기" if len(contents) == 1 else f"근거 문장 보기 ({len(contents)}개)"
            with st.expander(label):
                for item in contents:
                    if len(contents) > 1 and item.get("section"):
                        st.caption(item["section"])
                    st.write(item["content"])
