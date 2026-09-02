"""Track C Streamlit MVP entry point."""

import streamlit as st

import theme
from tabs import chat, evaluation, explore, pipeline, process


st.set_page_config(page_title="문화유산 AI 안내", page_icon="🏛️", layout="wide")


def main() -> None:
    theme.apply()
    theme.hero(
        eyebrow="한국민족문화대백과사전 기반",
        title="🏛️ 문화유산 AI 안내",
        description=(
            "공식 자료를 근거로 답하고, 출처와 근거 문장을 함께 보여 드립니다. "
            "근거가 부족하면 추측하지 않고 답변을 보류합니다."
        ),
        stats=[
            ("75,835", "수집한 백과사전 항목"),
            ("179,028", "검색 가능한 원문 조각"),
            ("3단계", "쉽게 · 일반 · 깊이 있게"),
        ],
    )

    chat_tab, process_tab, pipeline_tab, evaluation_tab, explore_tab = st.tabs(
        ["질문하기", "답변 과정", "파이프라인", "평가 결과", "문화유산 네트워크"]
    )
    with chat_tab:
        chat.render()
    with process_tab:
        process.render()
    with pipeline_tab:
        pipeline.render()
    with evaluation_tab:
        evaluation.render()
    with explore_tab:
        explore.render()


if __name__ == "__main__":
    main()
