"""Response-type-specific UI cards."""

import json

import streamlit as st

import rag_client


def render(response: dict) -> None:
    response_type = response["response_type"]

    if response_type == "needs_clarification":
        _render_clarification(response)
    elif response_type == "corrected_premise":
        _render_correction(response)
    elif response_type == "insufficient_evidence":
        st.warning(response["message"])
    elif response_type in {"safety_refusal", "out_of_scope"}:
        st.info(response["message"])
    else:
        st.markdown("#### 답변")
        st.write(response["message"])
        _listen_button("answer", response["message"])


def _render_clarification(response: dict) -> None:
    clarification = response.get("clarification") or {}
    compound = clarification.get("reason_code") == rag_client.COMPOUND_REASON_CODE
    st.markdown("#### 🧩 한 번에 하나씩 물어봐 주세요" if compound else "#### 🤔 어떤 대상을 말씀하셨나요?")
    st.write(clarification.get("question", response["message"]))
    _listen_button("clarification", clarification.get("question", response["message"]))

    # 계약 0.3.0-draft: 선택지는 {id, label, source_chunk_ids} 객체다.
    options = [option for option in clarification.get("options", []) if isinstance(option, dict)][:3]
    columns = st.columns(max(1, len(options)))
    for index, (column, option) in enumerate(zip(columns, options, strict=False)):
        label = str(option.get("label") or option.get("id") or "선택지")
        option_id = str(option.get("id") or f"option-{index + 1}")
        with column:
            if st.button(label, use_container_width=True, key=f"clarify-{option_id}"):
                _select_clarification(response, clarification, option)
                st.rerun()

    typed = st.text_input(
        "직접 입력하기",
        key="clarification_input",
        placeholder="질문을 하나만 입력하세요" if compound else "대상을 직접 입력하세요",
    )
    if st.button("이 내용으로 다시 질문", key="clarify-typed", use_container_width=True):
        if typed.strip():
            _select_clarification(response, clarification, {"id": "typed", "label": typed.strip()})
            st.rerun()
        else:
            st.warning("확인할 대상을 입력해 주세요.")


def _select_clarification(response: dict, clarification: dict, option: dict) -> None:
    """선택 결과를 다음 요청으로 넘긴다.

    복합 질문은 대상을 되묻는 게 아니라 **어느 질문을 할지** 고르는 것이므로,
    고른 문장을 그대로 새 질문으로 보낸다. ClarificationContext를 실어 보내면
    RagService가 같은 복합 질문을 다시 받아 근거 부족으로 처리한다.
    """
    result = st.session_state.get("last_result", {})
    original = result.get("question", "")
    label = str(option.get("label", "")).strip()

    if clarification.get("reason_code") == rag_client.COMPOUND_REASON_CODE:
        st.session_state["pending_question"] = label or original
        st.session_state["pending_autorun"] = True
        return

    st.session_state["clarification_context"] = {
        "original_question": original,
        "clarification_question": clarification.get("question", ""),
        "clarification_response": str(option.get("label", "")),
        "clarification_turn_count": 1,
    }
    st.session_state["interaction_id"] = response.get("interaction_id")
    st.session_state["pending_question"] = original


def _render_correction(response: dict) -> None:
    correction = response.get("premise_correction") or {}
    st.markdown("#### ⓘ 확인된 정보")
    st.write(correction.get("corrected_premise", response["message"]))
    _listen_button("correction", correction.get("corrected_premise", response["message"]))


def _js_string(text: str) -> str:
    """답변 문장을 JS 문자열 리터럴로 안전하게 감싼다.

    `json.dumps`는 `<`를 그대로 두기 때문에 본문에 `</script>`가 들어 있으면
    script 태그를 빠져나갈 수 있다. 답변과 근거 문장은 검색된 원문과 LLM 출력에서
    오므로 신뢰할 수 없는 입력으로 다룬다.
    """
    return json.dumps(text, ensure_ascii=False).replace("<", r"\u003c")


def _listen_button(key: str, text: str) -> None:
    """Read the displayed response through the browser's built-in Korean TTS."""
    if st.button("🔊 안내 듣기", key=f"listen-{key}"):
        st.iframe(
            f"""
            <script>
              window.speechSynthesis.cancel();
              const utterance = new SpeechSynthesisUtterance({_js_string(text)});
              utterance.lang = "ko-KR";
              utterance.rate = 1;
              window.speechSynthesis.speak(utterance);
            </script>
            """,
            # st.iframe은 height=0을 허용하지 않는다. 소리만 내므로 1px로 숨긴다.
            height=1,
        )
