"""Citation and evidence rendering components."""

import streamlit as st

from mock_responses import SOURCE_NAME


def render(citations: list[dict]) -> None:
    if not citations:
        return

    st.subheader("출처와 근거")
    for index, item in enumerate(citations, start=1):
        title = item.get("title") or "제목 없는 자료"
        section = item.get("section")
        source_url = item.get("source_url")

        with st.container(border=True):
            st.markdown(f"**{index}. {title}**")
            details = SOURCE_NAME if not section else f"{SOURCE_NAME} · {section}"
            st.caption(details)
            if source_url:
                st.link_button("공식 원문 보기 ↗", source_url, key=f"source-{index}")
            content = item.get("content")
            if content:
                with st.expander("근거 문장 보기"):
                    st.write(content)
