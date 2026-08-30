"""Track C Streamlit MVP entry point."""

import streamlit as st

from tabs import chat, evaluation, explore, process


st.set_page_config(page_title="문화유산 AI 안내", page_icon="🏛️", layout="wide")


def main() -> None:
    st.title("🏛️ 문화유산 AI 안내")
    st.caption("공식 자료를 근거로 답하고, 출처와 근거 문장을 함께 보여 드립니다.")

    chat_tab, process_tab, evaluation_tab, explore_tab = st.tabs(
        ["질문하기", "답변 과정", "평가 결과", "문화유산 탐험 지도"]
    )
    with chat_tab:
        chat.render()
    with process_tab:
        process.render()
    with evaluation_tab:
        evaluation.render()
    with explore_tab:
        explore.render()


if __name__ == "__main__":
    main()
