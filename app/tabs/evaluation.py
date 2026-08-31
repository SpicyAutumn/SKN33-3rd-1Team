"""검색 품질 실측치와 답변 품질 평가 상태를 함께 보여 준다."""

from html import escape

import streamlit as st

import retrieval


# 답변 품질 지표는 LLM 심사가 있어야 계산할 수 있다. 지금은 점수를 만들지 않고
# 무엇을 재는 지표인지와 낮을 때 볼 곳만 안내한다.
ANSWER_METRICS = {
    "faithfulness": {
        "title": "Faithfulness",
        "short": "답변이 검색 근거에 충실한가",
        "definition": "최종 답변의 내용이 검색된 청크 안에 있는 사실에만 근거하는지 확인합니다.",
        "improvement": "점수가 낮으면 답변에 근거 문서에 없는 설명이 추가되었는지 확인하고, 답변 범위를 줄입니다.",
    },
    "answer_relevancy": {
        "title": "Answer Relevancy",
        "short": "답변이 질문에 관련 있는가",
        "definition": "최종 답변이 사용자가 던진 질문에 직접 답하는지 확인합니다.",
        "improvement": "점수가 낮으면 질문과 무관한 배경 설명을 줄이고, 질문의 핵심부터 답합니다.",
    },
    "context_precision": {
        "title": "Context Precision",
        "short": "상위 검색 청크가 적절한가",
        "definition": "상위에 검색된 청크가 질문과 관련 있고, 중요한 근거가 앞순위에 있는지 확인합니다.",
        "improvement": "점수가 낮으면 top_k, 메타데이터 필터, 재정렬 방식을 조정합니다.",
    },
    "context_recall": {
        "title": "Context Recall",
        "short": "필요한 근거를 충분히 찾았는가",
        "definition": "정답에 필요한 정보가 검색된 청크 안에 충분히 포함되어 있는지 확인합니다.",
        "improvement": "점수가 낮으면 검색 범위를 넓히거나 청킹 방식과 임베딩 입력을 점검합니다.",
    },
}


def _score(context: dict) -> float | None:
    value = context.get("retrieval_score")
    return float(value) if isinstance(value, (int, float)) else None


def render() -> None:
    st.subheader("평가 결과")

    result = st.session_state.get("last_result")
    if not result:
        st.info("질문하기 탭에서 답변을 받은 뒤 이 탭을 확인해 주세요.")
        return

    contexts = result.get("retrieved_contexts", [])
    used = set(result.get("used_chunk_ids", []))

    _render_retrieval_quality(contexts, used)
    st.divider()
    _render_answer_quality()


def _render_retrieval_quality(contexts: list[dict], used: set[str]) -> None:
    st.markdown("#### 검색 품질")
    st.caption("이번 질문에서 실제로 측정한 값입니다.")

    if not contexts:
        st.warning("검색 결과가 없어 측정할 값이 없습니다.")
        return

    scores = [s for s in (_score(c) for c in contexts) if s is not None]
    passed = [c for c in contexts if retrieval.meets_threshold(c)]
    documents = {c.get("document_id") for c in contexts if c.get("document_id")}

    columns = st.columns(4)
    columns[0].metric("검색된 조각", f"{len(contexts)}건")
    columns[1].metric(
        "기준선 통과",
        f"{len(passed)}건",
        delta=f"탈락 {len(contexts) - len(passed)}건" if len(passed) < len(contexts) else None,
        delta_color="off",
    )
    columns[2].metric(
        "검색된 문서",
        f"{len(documents)}개",
        delta="중복 있음" if len(documents) < len(contexts) else "중복 없음",
        delta_color="off",
        help="검색된 조각 전체가 몇 개 문서에서 나왔는지입니다. 기준선 통과 여부와 무관합니다.",
    )
    columns[3].metric(
        "최고 유사도",
        f"{max(scores):.3f}" if scores else "—",
        delta=f"1·2위 격차 {scores[0] - scores[1]:+.3f}" if len(scores) >= 2 else None,
        delta_color="off",
    )

    st.markdown("##### 유사도 분포")
    _render_score_bars(contexts, used)

    for note in _observations(contexts, documents, scores):
        st.caption(f"· {note}")


def _render_score_bars(contexts: list[dict], used: set[str]) -> None:
    """조각별 유사도를 막대로 그리고 기준선 통과 여부를 색으로 구분한다."""
    scores = [s for s in (_score(c) for c in contexts) if s is not None]
    ceiling = max(scores + [retrieval.EVIDENCE_MIN_SCORE]) * 1.15 if scores else 1.0

    rows = []
    for context in contexts:
        score = _score(context)
        is_used = context.get("chunk_id") in used
        passes = retrieval.meets_threshold(context)
        width = (score / ceiling * 100) if score is not None else 0.0
        state = "used" if is_used else ("pass" if passes else "drop")
        label = "답변에 사용" if is_used else ("기준선 통과" if passes else "기준선 미달")
        score_text = f"{score:.3f}" if score is not None else "—"
        title = escape(str(context.get("title", "제목 없음")))
        rank = escape(str(context.get("retrieval_rank", "-")))
        rows.append(
            f'<div class="eval-row eval-{state}">'
            f'<span class="eval-rank">{rank}위</span>'
            f'<span class="eval-track"><span class="eval-bar" style="width:{width:.1f}%"></span></span>'
            f'<span class="eval-score">{score_text}</span>'
            f'<span class="eval-title">{title}</span>'
            f'<span class="eval-tag">{label}</span>'
            f"</div>"
        )

    threshold_pct = retrieval.EVIDENCE_MIN_SCORE / ceiling * 100
    st.html(
        f'<div class="eval-chart" style="--eval-threshold:{threshold_pct:.1f}%">'
        + "".join(rows)
        + f'<p class="eval-note">점선 = 기준선 {retrieval.EVIDENCE_MIN_SCORE:.2f}</p>'
        + "</div>"
    )


def _observations(contexts: list[dict], documents: set[str], scores: list[float]) -> list[str]:
    notes = []
    if len(documents) < len(contexts):
        notes.append(
            f"조각 {len(contexts)}건이 문서 {len(documents)}개에서 나왔습니다. "
            "같은 문서 조각이 상위 자리를 나눠 갖고 있습니다."
        )
    if len(scores) >= 3:
        spread = scores[1] - scores[-1]
        if spread < 0.05:
            notes.append(
                f"2위부터 {len(scores)}위까지 점수 차이가 {spread:.3f}뿐이라 "
                "그 구간의 순위는 변별력이 낮습니다."
            )
    if scores and scores[0] < retrieval.EVIDENCE_MIN_SCORE:
        notes.append("모든 조각이 기준선에 못 미쳐 답변을 보류했습니다.")
    return notes


def _render_answer_quality() -> None:
    st.markdown("#### 답변 품질")
    st.caption(
        "RAGAS 기준 네 가지입니다. LLM 심사가 연결되지 않아 아직 점수를 계산하지 않습니다. "
        "값을 지어내지 않고 미연결 상태로 둡니다."
    )

    columns = st.columns(4)
    for column, detail in zip(columns, ANSWER_METRICS.values(), strict=True):
        column.metric(detail["title"], "—", help=detail["short"])

    for detail in ANSWER_METRICS.values():
        with st.expander(f"{detail['title']} · {detail['short']}"):
            st.markdown("**무엇을 평가하나요?**")
            st.write(detail["definition"])
            st.markdown("**점수가 낮을 때 확인할 점**")
            st.write(detail["improvement"])
