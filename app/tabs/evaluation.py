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
    documents = {c.get("document_id") for c in contexts if c.get("document_id")}

    columns = st.columns(4)
    columns[0].metric("검색된 조각", f"{len(contexts)}건")
    columns[1].metric(
        "답변에 사용",
        f"{len(used)}건",
        delta=f"쓰지 않음 {len(contexts) - len(used)}건" if len(used) < len(contexts) else None,
        delta_color="off",
        help="검색된 조각 중 근거로 전달한 것입니다.",
    )
    columns[2].metric(
        "검색된 문서",
        f"{len(documents)}개",
        delta="중복 있음" if len(documents) < len(contexts) else "중복 없음",
        delta_color="off",
        help="검색된 조각 전체가 몇 개 문서에서 나왔는지입니다.",
    )
    # 하이브리드는 낱말 일치도 함께 보므로 순위와 유사도 순서가 어긋날 수 있다.
    # `1·2위 격차` 같은 표기는 그 전제가 깨지면 음수가 되어 뜻이 통하지 않는다.
    columns[3].metric(
        f"{retrieval.SCORE_NAME} 범위",
        f"{max(scores):.3f}" if scores else "—",
        delta=f"최저 {min(scores):.3f}" if len(scores) >= 2 else None,
        delta_color="off",
        help=retrieval.score_caption().replace("**", ""),
    )

    st.markdown(f"##### {retrieval.SCORE_NAME} 분포")
    st.caption(retrieval.score_caption())
    _render_score_bars(contexts, used)

    for note in _observations(contexts, documents, scores):
        st.caption(f"· {note}")


def _render_score_bars(contexts: list[dict], used: set[str]) -> None:
    """조각별 유사도를 막대로 그리고 기준선 통과 여부를 색으로 구분한다."""
    scores = [s for s in (_score(c) for c in contexts) if s is not None]
    ceiling = max(scores) * 1.15 if scores else 1.0

    rows = []
    for context in contexts:
        score = _score(context)
        is_used = context.get("chunk_id") in used
        width = (score / ceiling * 100) if score is not None else 0.0
        state = "used" if is_used else "pass"
        label = "답변에 사용" if is_used else "검색됨"
        score_text = retrieval.format_score(score)
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

    note = f"{retrieval.retrieval_label()} · 순위는 검색 결과 순서입니다."
    st.html(
        '<div class="eval-chart" style="--eval-threshold:0%">'
        + "".join(rows)
        + f'<p class="eval-note">{escape(note)}</p>'
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
        spread = max(scores) - min(scores)
        if spread < 0.05:
            notes.append(
                f"조각 {len(scores)}건의 {retrieval.SCORE_NAME} 차이가 {spread:.3f}뿐이라 "
                "이 값만으로는 순위를 가리기 어렵습니다."
            )
    ranked = [s for s in (_score(c) for c in contexts) if s is not None]
    if len(ranked) >= 2 and ranked != sorted(ranked, reverse=True):
        notes.append(
            f"이번 결과는 순위가 {retrieval.SCORE_NAME} 순서와 다릅니다. "
            "낱말 일치를 함께 보고 순위를 정했다는 뜻이며, 순위가 잘못된 것이 아닙니다."
        )
    missing = len(contexts) - len(scores)
    if missing:
        notes.append(
            f"{missing}건은 낱말 검색으로만 올라와 {retrieval.SCORE_NAME}를 재지 않았습니다."
        )
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
