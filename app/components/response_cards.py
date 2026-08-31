"""Response-type-specific UI cards."""

import json

import streamlit as st
import streamlit.components.v1 as components


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
    st.markdown("#### 🤔 어떤 대상을 말씀하셨나요?")
    st.write(clarification.get("question", response["message"]))
    _listen_button("clarification", clarification.get("question", response["message"]))

    options = clarification.get("options", [])[:3]
    columns = st.columns(max(1, len(options)))
    for column, option in zip(columns, options, strict=False):
        with column:
            if st.button(option, use_container_width=True, key=f"option-{option}"):
                st.session_state["selected_clarification"] = option
                st.success(f"‘{option}’을 선택했습니다. 실제 RAG 연결 후 이 값을 다음 질문에 전달합니다.")

    left, right = st.columns(2)
    with left:
        st.text_input("직접 입력하기", key="clarification_input", placeholder="대상을 직접 입력하세요")
    with right:
        st.button("다른 후보 찾기", key="more-candidates", use_container_width=True)


def _render_correction(response: dict) -> None:
    correction = response.get("premise_correction") or {}
    st.markdown("#### ⓘ 확인된 정보")
    st.write(correction.get("corrected_premise", response["message"]))
    _listen_button("correction", correction.get("corrected_premise", response["message"]))


def _listen_button(key: str, text: str) -> None:
    """Read the displayed response through the browser's built-in Korean TTS."""
    if st.button("🔊 안내 듣기", key=f"listen-{key}"):
        escaped_text = json.dumps(text, ensure_ascii=False)
        components.html(
            f"""
            <script>
              window.speechSynthesis.cancel();
              const utterance = new SpeechSynthesisUtterance({escaped_text});
              utterance.lang = "ko-KR";
              utterance.rate = 1;
              window.speechSynthesis.speak(utterance);
            </script>
            """,
            height=0,
        )
