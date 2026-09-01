"""Question and answer tab."""

import logging
from copy import deepcopy

import streamlit as st

import retrieval
from components import citations, response_cards
from mock_responses import RESPONSES


logger = logging.getLogger(__name__)

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

    live = retrieval.is_live()
    if live:
        st.caption("✅ 실제 검색 연결됨 — Pinecone에서 근거를 찾습니다. 답변 문장 생성은 아직 준비 중입니다.")
    else:
        # [제거 예정] .env 키를 받으면 이 안내와 아래 응답 유형 선택 항목을 함께 지운다.
        st.caption("🔧 Mock 응답 모드 — 화면 확인용입니다. `.env`에 키를 넣으면 실제 검색으로 자동 전환됩니다.")
        with st.expander("실제 검색을 켜려면"):
            st.write("프로젝트 최상위 `.env`에 아래 값을 채우면 됩니다.")
            st.code("\n".join(f"{name}=" for name in retrieval.REQUIRED_ENV), language="ini")
            st.caption(f"현재 비어 있는 항목: {', '.join(retrieval.missing_env())}")

    pending_question = st.session_state.pop("pending_question", None)
    autorun = st.session_state.pop("pending_autorun", False)
    if pending_question:
        st.session_state["question"] = pending_question
    pending_level = st.session_state.pop("pending_audience_level", None)
    if pending_level:
        st.session_state["audience_level"] = pending_level
    st.session_state.setdefault("audience_level", retrieval.DEFAULT_AUDIENCE_LEVEL)

    with st.form("question_form"):
        question = st.text_input("질문", placeholder="예: 길쌈노래는 무엇인가요?", key="question")
        # 입력 전체를 하나의 질문으로 검색한다. 여러 질문을 한 번에 넣으면 일부 근거가 빠진다.
        st.caption("한 번에 하나의 문화유산이나 한 가지 내용을 질문하면 더 정확한 답변을 받을 수 있어요.")
        st.radio(
            "설명 수준",
            options=retrieval.AUDIENCE_LEVELS,
            format_func=retrieval.AUDIENCE_LABELS.get,
            horizontal=True,
            key="audience_level",
            help="같은 근거를 어느 정도 깊이로 설명할지 고릅니다. 답변 뒤에도 바꿀 수 있습니다.",
        )
        if not live:
            # [제거 예정] 실제 검색이 붙으면 응답 유형은 서버가 정하므로 이 선택 항목은 사라진다.
            st.selectbox(
                "화면 확인용 응답 유형", options=list(LABELS), format_func=LABELS.get, key="response_type"
            )
        submitted = st.form_submit_button("답변 받기", type="primary", use_container_width=True)

    if submitted:
        if not question.strip():
            st.warning("질문을 입력해 주세요.")
        else:
            _run(question.strip(), st.session_state["audience_level"], live=live)
    elif autorun and pending_question:
        # 되묻기에서 질문을 고른 경우다. 고른 즉시 실행한다.
        _run(pending_question, st.session_state["audience_level"], live=live)

    result = st.session_state.get("last_result")
    if not result:
        st.info("질문을 입력하고 ‘답변 받기’를 누르면 답변 과정과 평가 결과 탭에도 같은 결과가 표시됩니다.")
        return

    response = result["response"]
    response_cards.render(response)
    _render_level_switch(result, live=live)
    citations.render(response.get("citations", []))


def _run(question: str, audience_level: str, *, live: bool) -> None:
    """질문을 처리해 결과를 세션에 저장한다."""
    execution = _fetch(question, audience_level, live=live)
    if execution is None:
        return
    response = execution["response"]
    st.session_state["last_result"] = {
        "question": question,
        "audience_level": response.get("audience_level", audience_level),
        "response": response,
        "retrieved_contexts": execution.get("retrieved_contexts", []),
        "used_chunk_ids": execution.get("used_chunk_ids", []),
        "retrieval_top_k": execution.get("retrieval_top_k"),
        "related_keywords": response.get("related_topics", []),
    }
    # ServiceResponse에는 retrieved_contexts가 없다. 실제 검색 결과는 실행 추적에서 읽는다.
    contexts = execution.get("retrieved_contexts", [])
    history = st.session_state.setdefault("question_history", [])
    history.append(
        {
            "question": question,
            "title": next(
                (context.get("title") for context in contexts if context.get("title")),
                "검색 결과 없음",
            ),
        }
    )
    st.session_state["question_history"] = history[-10:]


def _render_level_switch(result: dict, *, live: bool) -> None:
    """답변 뒤에 설명 수준만 한 단계씩 바꾸는 버튼."""
    current = result.get("audience_level", retrieval.DEFAULT_AUDIENCE_LEVEL)
    question = result.get("question", "")
    if not question:
        return

    st.caption(f"현재 설명 수준: **{retrieval.AUDIENCE_LABELS.get(current, current)}**")
    easier, deeper = st.columns(2)
    with easier:
        if st.button(
            "🙂 더 쉽게 설명",
            use_container_width=True,
            disabled=current == retrieval.AUDIENCE_LEVELS[0],
            key="level-easier",
        ):
            _request_level(question, retrieval.shift_level(current, -1), live=live)
    with deeper:
        if st.button(
            "🔎 더 자세히 설명",
            use_container_width=True,
            disabled=current == retrieval.AUDIENCE_LEVELS[-1],
            key="level-deeper",
        ):
            _request_level(question, retrieval.shift_level(current, 1), live=live)


def _request_level(question: str, level: str, *, live: bool) -> None:
    """같은 질문을 다른 설명 수준으로 다시 묻는다."""
    # 선택 위젯은 다음 실행에서 갱신되므로 pending 값으로 넘긴다.
    st.session_state["pending_question"] = question
    st.session_state["pending_audience_level"] = level
    _run(question, level, live=live)
    st.rerun()


def _fetch(question: str, audience_level: str, *, live: bool) -> dict | None:
    """RagService를 호출한다. 키가 없으면 Mock 응답을 같은 형식으로 감싸 돌려준다."""
    if live:
        with st.spinner("공식 자료를 검색하고 있습니다…"):
            try:
                return retrieval.answer(
                    question,
                    audience_level=audience_level,
                    interaction_id=st.session_state.pop("interaction_id", None),
                    clarification_context=st.session_state.pop("clarification_context", None),
                )
            except Exception:  # noqa: BLE001
                # 내부 오류 원문은 화면에 노출하지 않고 서버 로그로만 남긴다.
                logger.exception("RAG 서비스 호출 실패: question=%r", question)
                st.error(
                    "지금은 자료를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요. "
                    "문제가 계속되면 실행 환경의 API 키 설정을 확인해 주세요."
                )
                return None

    # [제거 예정] 아래 Mock 분기는 실제 검색이 안정화되면 통째로 삭제한다.
    response = deepcopy(RESPONSES[st.session_state.get("response_type", "answered")])
    response["audience_level"] = audience_level
    return {
        "response": response,
        "retrieved_contexts": response.get("retrieved_contexts", []),
        "used_chunk_ids": response.get("used_chunk_ids", []),
        "retrieval_top_k": len(response.get("retrieved_contexts", [])),
    }
