"""Display the retrieval trace for the current question."""

import streamlit as st

import retrieval


def render() -> None:
    st.subheader("답변이 만들어지는 과정")
    st.caption("현재 질문에서 실제로 검색된 청크와 답변에 사용된 근거를 표시합니다.")

    result = st.session_state.get("last_result")
    if not result:
        st.info("질문하기 탭에서 답변을 받은 뒤 이 탭을 확인해 주세요.")
        return

    response = result["response"]
    contexts = result["retrieved_contexts"]
    used_chunk_ids = set(result["used_chunk_ids"])

    with st.container(border=True):
        st.markdown("**1. 사용자 질문**")
        st.write(result["question"])

    with st.container(border=True):
        st.markdown("**2. 검색된 공식 자료 청크**")
        score_name = retrieval.score_label(contexts)
        if not contexts:
            st.write("이번 응답에는 답변에 사용할 수 있는 검색 청크가 없습니다.")
        for index, context in enumerate(contexts, start=1):
            rank = context.get("retrieval_rank", index)
            score = context.get("retrieval_score")
            used = context.get("chunk_id") in used_chunk_ids
            label = "✅ 답변에 사용됨" if used else "검색 결과"
            # 검색기에 따라 점수 척도가 다르다. 하이브리드 결과는 유사도가 아니다.
            score_text = (
                f" · {score_name} {retrieval.format_score(score, contexts)}"
                if isinstance(score, (int, float))
                else ""
            )
            with st.expander(f"{rank}위 · {context.get('title', '제목 없음')}{score_text} · {label}", expanded=used):
                st.write(context.get("content", "본문 없음"))
                st.caption(f"section: {context.get('section', '없음')} · chunk_id: {context.get('chunk_id', '없음')}")

    with st.container(border=True):
        st.markdown("**3. 최종 응답**")
        st.caption(f"응답 유형: {response['response_type']}")
        st.write(response["message"])
