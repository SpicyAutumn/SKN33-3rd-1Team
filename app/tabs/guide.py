"""Service guidance tab."""

import streamlit as st


def render() -> None:
    st.subheader("서비스 안내")
    st.write("이 서비스는 한국민족문화대백과사전의 공식 자료를 바탕으로 문화유산 정보를 안내합니다.")
    st.markdown(
        """
        - 답변에는 공식 원문 링크와 근거 문장을 함께 표시합니다.
        - 자료가 부족하면 추측하지 않고 확인이 어렵다고 안내합니다.
        - 질문의 대상이 모호하면 한 번만 추가로 확인합니다.
        - 잘못된 전제는 공식 근거가 있을 때 부드럽게 바로잡습니다.
        """
    )
