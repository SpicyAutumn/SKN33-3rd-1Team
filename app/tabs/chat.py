"""Question and answer tab."""

from copy import deepcopy

import streamlit as st

from components import citations, response_cards
from mock_responses import RESPONSES


LABELS = {
    "answered": "정상 답변",
    "insufficient_evidence": "근거 부족",
    "needs_clarification": "추가 질문 필요",
    "corrected_premise": "전제 정정",
    "safety_refusal": "안전 거절",
    "out_of_scope": "범위 밖 질문",
}


def render() -> None:
    st.subheader("문화유산에 대해 질문해 보세요")
    st.caption("현재는 UI 확인을 위한 Mock 응답 모드입니다. 실제 RAG 연결 뒤에는 이 선택 항목을 제거합니다.")

    pending_question = st.session_state.pop("pending_question", None)
    if pending_question:
        st.session_state["question"] = pending_question

    with st.form("question_form"):
        question = st.text_input("질문", placeholder="예: 길쌈노래는 무엇인가요?", key="question")
        response_type = st.selectbox(
            "화면 확인용 응답 유형", options=list(LABELS), format_func=LABELS.get, key="response_type"
        )
        submitted = st.form_submit_button("답변 받기", type="primary", use_container_width=True)

    if submitted:
        if not question.strip():
            st.warning("질문을 입력해 주세요.")
        else:
            response = deepcopy(RESPONSES[response_type])
            st.session_state["last_result"] = {
                "question": question.strip(),
                "response": response,
                "retrieved_contexts": response.get("retrieved_contexts", []),
                "used_chunk_ids": response.get("used_chunk_ids", []),
                "related_keywords": response.get("related_keywords", []),
            }
            history = st.session_state.setdefault("question_history", [])
            history.append(
                {
                    "question": question.strip(),
                    "title": next(
                        (context.get("title") for context in response.get("retrieved_contexts", []) if context.get("title")),
                        "검색 결과 없음",
                    ),
                }
            )
            st.session_state["question_history"] = history[-10:]

    result = st.session_state.get("last_result")
    if not result:
        st.info("질문을 입력하고 ‘답변 받기’를 누르면 답변 과정과 평가 결과 탭에도 같은 결과가 표시됩니다.")
        return

    response = result["response"]
    response_cards.render(response)
    citations.render(response.get("citations", []))
