"""RAGAS-style evaluation display for the current response."""

import streamlit as st


MOCK_SCORES = {
    "faithfulness": 0.92,
    "answer_relevancy": 0.89,
    "context_precision": 0.86,
    "context_recall": 0.90,
}

METRIC_DETAILS = {
    "faithfulness": {
        "title": "Faithfulness",
        "definition": "최종 답변의 내용이 검색된 청크 안에 있는 사실에만 근거하는지 확인합니다.",
        "mock_reason": "답변의 핵심인 ‘여성들이 길쌈을 하며 부르는 민요’가 1위 검색 청크에 직접 들어 있습니다.",
        "improvement": "점수가 낮으면 답변에 근거 문서에 없는 설명이 추가되었는지 확인하고, 답변 범위를 줄입니다.",
    },
    "answer_relevancy": {
        "title": "Answer Relevancy",
        "definition": "최종 답변이 사용자가 던진 질문에 직접 답하는지 확인합니다.",
        "mock_reason": "질문의 대상과 정의를 바로 설명해 질문 의도에 맞습니다.",
        "improvement": "점수가 낮으면 질문과 무관한 배경 설명을 줄이고, 질문의 핵심부터 답합니다.",
    },
    "context_precision": {
        "title": "Context Precision",
        "definition": "상위에 검색된 청크가 질문과 관련 있고, 중요한 근거가 앞순위에 있는지 확인합니다.",
        "mock_reason": "1위 청크가 길쌈노래의 정의를 직접 설명하고, 나머지 청크는 관련 용어와 분류를 보완합니다.",
        "improvement": "점수가 낮으면 top_k, 메타데이터 필터, 재정렬 방식을 조정합니다.",
    },
    "context_recall": {
        "title": "Context Recall",
        "definition": "정답에 필요한 정보가 검색된 청크 안에 충분히 포함되어 있는지 확인합니다.",
        "mock_reason": "정의·기능·분류 청크가 함께 검색되어 답변에 필요한 핵심 정보를 확인할 수 있습니다.",
        "improvement": "점수가 낮으면 검색 범위를 넓히거나 청킹 방식과 임베딩 입력을 점검합니다.",
    },
}

MOCK_JUDGE_FEEDBACK = {
    "overall_verdict": "통과",
    "overall_reason": "답변의 핵심 정의가 검색된 1위 청크에 직접 포함되어 있고, 질문에도 바로 답합니다.",
    "metrics": {
        "faithfulness": {
            "verdict": "근거 일치",
            "reason": "‘길쌈을 하면서 부르는 민요’라는 답변의 핵심 내용이 검색된 근거 문장과 일치합니다.",
        },
        "answer_relevancy": {
            "verdict": "질문 적합",
            "reason": "길쌈노래의 의미를 묻는 질문에 정의와 역할을 설명했습니다.",
        },
        "context_precision": {
            "verdict": "상위 청크 적절",
            "reason": "가장 관련 있는 정의 청크가 1위에 배치되어 있습니다.",
        },
        "context_recall": {
            "verdict": "핵심 근거 확보",
            "reason": "답변에 필요한 정의와 보조 설명을 검색 청크에서 확인할 수 있습니다.",
        },
    },
    "improvement": "현재 사례에서는 추가 조치가 필요하지 않습니다. 실제 평가에서는 낮은 점수 사례를 함께 검토합니다.",
}


def render() -> None:
    st.subheader("평가 결과")
    st.caption("RAGAS의 Faithfulness, Answer Relevancy, Context Precision, Context Recall 기준을 사용합니다.")

    result = st.session_state.get("last_result")
    if not result:
        st.info("질문하기 탭에서 답변을 받은 뒤 이 탭을 확인해 주세요.")
        return

    response = result["response"]
    if response["response_type"] not in {"answered", "corrected_premise"}:
        st.info("근거를 이용해 생성한 답변 유형에서만 RAGAS 평가 점수를 표시합니다.")
        return

    st.caption("현재는 화면 연결을 위한 Mock 점수입니다. 실제 RAGAS 실행 결과 CSV가 준비되면 이 값을 교체합니다.")
    labels = {
        "faithfulness": ("Faithfulness", "답변이 검색 근거에 충실한가"),
        "answer_relevancy": ("Answer Relevancy", "답변이 질문에 관련 있는가"),
        "context_precision": ("Context Precision", "상위 검색 청크가 적절한가"),
        "context_recall": ("Context Recall", "필요한 근거를 충분히 찾았는가"),
    }
    columns = st.columns(4)
    for column, key in zip(columns, labels, strict=True):
        title, help_text = labels[key]
        column.metric(title, f"{MOCK_SCORES[key]:.2f}", help=help_text)

    st.markdown("#### 점수별 평가 근거")
    for key, detail in METRIC_DETAILS.items():
        with st.expander(f"{detail['title']} · {MOCK_SCORES[key]:.2f}", expanded=False):
            st.markdown("**무엇을 평가하나요?**")
            st.write(detail["definition"])
            st.markdown("**이번 결과 해석**")
            st.write(detail["mock_reason"])
            st.markdown("**점수가 낮을 때 확인할 점**")
            st.write(detail["improvement"])

    with st.expander("LLM 심사 의견 보기", expanded=True):
        st.caption("현재는 화면 시연용 Mock 심사 의견입니다. 실제 연결 시 LLM-as-a-Judge 결과를 이 형식으로 전달받습니다.")
        st.markdown(f"**종합 판정: {MOCK_JUDGE_FEEDBACK['overall_verdict']}**")
        st.write(MOCK_JUDGE_FEEDBACK["overall_reason"])
        for key, detail in METRIC_DETAILS.items():
            feedback = MOCK_JUDGE_FEEDBACK["metrics"][key]
            st.markdown(f"**{detail['title']} — {feedback['verdict']}**")
            st.write(feedback["reason"])
        st.markdown("**개선 제안**")
        st.write(MOCK_JUDGE_FEEDBACK["improvement"])

    with st.expander("이 결과가 평가된 근거 보기", expanded=True):
        st.markdown("**질문**")
        st.write(result["question"])
        st.markdown("**검색된 근거**")
        for context in result["retrieved_contexts"]:
            st.write(f"- {context.get('content', '')}")
        st.markdown("**서비스 답변**")
        st.write(response["message"])
