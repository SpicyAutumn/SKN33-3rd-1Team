"""Response-type-specific UI cards."""

import json

import streamlit as st


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
