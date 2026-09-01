"""원문이 답변이 되기까지의 공정을 사용자 시점과 구현 시점으로 나란히 보여 준다.

값은 모두 이번 질문에서 실제로 나온 것이다. 아직 연결되지 않은 단계는
숫자를 지어내지 않고 준비 중으로 표시한다.
"""

import csv
from html import escape
from pathlib import Path

import streamlit as st

import retrieval

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = PROJECT_ROOT / "data" / "manifest.csv"

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
TOTAL_CHUNKS = 179_028


@st.cache_data(show_spinner=False)
def _manifest_index() -> dict[str, dict[str, str]]:
    """EID로 수집 기록을 찾기 위한 색인. 파일이 없으면 빈 값으로 둔다."""
    if not MANIFEST_PATH.exists():
        return {}
    index: dict[str, dict[str, str]] = {}
    with MANIFEST_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            eid = (row.get("eid") or "").strip()
            if eid:
                index[eid] = row
    return index


def _score(context: dict) -> float | None:
    value = context.get("retrieval_score")
    return float(value) if isinstance(value, (int, float)) else None


def _meta(context: dict, key: str) -> str:
    value = str(context.get("metadata", {}).get(key, "") or "").strip()
    return "" if value.upper() == "NONE" else value


def _stage(number: int, user_side: str, system_side: str, *, pending: bool = False) -> str:
    state = " process-pending" if pending else ""
    return (
        f'<div class="process-stage{state}">'
        f'<div class="process-index">{number}</div>'
        f'<div class="process-user">{user_side}</div>'
        f'<div class="process-system">{system_side}</div>'
        f"</div>"
    )


def render() -> None:
    st.subheader("공정 견학")
    st.caption(
        "공장 견학처럼, 백과사전 원문이 답변이 되기까지의 공정을 그대로 열어 보여 드립니다. "
        "왼쪽은 사용자가 보는 화면, 오른쪽은 그때 시스템이 실제로 한 일입니다."
    )

    result = st.session_state.get("last_result")
    if not result:
        st.info("질문하기 탭에서 답변을 받은 뒤 이 탭을 확인해 주세요.")
        return

    response = result["response"]
    contexts = result.get("retrieved_contexts", [])
    used_ids = set(result.get("used_chunk_ids", []))
    scores = [s for s in (_score(c) for c in contexts) if s is not None]
    documents = {c.get("document_id") for c in contexts if c.get("document_id")}

    _render_flow(result, response, contexts, used_ids, scores, documents)
    _render_traceback(contexts, used_ids)


def _render_flow(result, response, contexts, used_ids, scores, documents) -> None:
    question = escape(result.get("question", ""))
    level = retrieval.AUDIENCE_LABELS.get(response.get("audience_level", ""), "일반 설명")
    score_range = (
        f"{retrieval.format_score(max(scores))} ~ {retrieval.format_score(min(scores))}"
        if scores
        else "측정값 없음"
    )
    mode = retrieval.retrieval_mode()
    if mode == "hybrid":
        indexed = retrieval.bm25_index_chunk_count()
        if indexed is None:
            coverage = "낱말 인덱스 크기 확인 불가"
        elif indexed < TOTAL_CHUNKS:
            # 부분 인덱스로도 검색은 된다. 닿지 못하는 문서가 있다는 걸 숨기지 않는다.
            coverage = (
                f"낱말 인덱스 {indexed:,}조각 — 전체 {TOTAL_CHUNKS:,}조각 중 일부만 들어 있습니다"
            )
        else:
            coverage = f"낱말 인덱스 {indexed:,}조각 — 전체"
        search_detail = (
            "뜻이 가까운 조각과 <b>같은 낱말이 든 조각</b>을 따로 찾아, 두 순위를 합칩니다."
            f"<br><span class='process-note'>{retrieval.retrieval_label()} · 상위 {len(contexts)}개</span>"
            f"<br><span class='process-note'>{coverage}</span>"
        )
    else:
        search_detail = (
            f"백과사전을 잘라 둔 조각들과 하나씩 비교해 <b>가까운 순서로 {len(contexts)}개</b>를 고릅니다."
            f"<br><span class='process-note'>{retrieval.retrieval_label()} · 낱말 검색 인덱스 없음</span>"
        )

    stages = [
        _stage(
            1,
            f"질문을 입력했습니다.<br><b>“{question}”</b><br><span class='process-note'>설명 수준: {level}</span>",
            f"질문 한 문장을 <b>{EMBEDDING_DIMENSIONS:,}개의 숫자</b>로 바꿉니다."
            f"<br><span class='process-note'>{EMBEDDING_MODEL}</span>",
        ),
        _stage(
            2,
            "‘공식 자료를 검색하고 있습니다…’",
            f"{search_detail}<br><span class='process-note'>{retrieval.SCORE_NAME} {score_range}"
            + ("  (참고값 · 순위와 순서가 다를 수 있습니다)" if retrieval.score_is_reference_only() else "")
            + "</span>",
        ),
        _stage(
            3,
            "<span class='process-note'>화면에는 보이지 않는 단계입니다.</span>",
            (
                "내용이 비어 있지 않은 조각을 <b>검색 순서 그대로</b> 근거로 넘깁니다."
                "<br>점수 기준선은 두지 않습니다."
                f"<br><span class='process-note'>조각 {len(contexts)}건 · "
                f"이 조각들이 나온 문서 {len(documents)}개</span>"
            ),
        ),
    ]

    if response["response_type"] == "answered":
        stages.append(
            _stage(
                4,
                f"답변과 <b>근거 {len(used_ids)}건</b>이 보입니다.<br>‘근거 문장 보기’를 펼치면 원문이 나옵니다.",
                f"<b>{len(used_ids)}개</b> 조각을 근거로 전달합니다. 출처 카드에서는 같은 문서끼리 묶어 보여 줍니다."
                f"<br><span class='process-note'>나머지 {max(len(contexts) - len(used_ids), 0)}건은 화면에 쓰지 않았습니다.</span>",
            )
        )
    else:
        stages.append(
            _stage(
                4,
                "‘확인하기 어렵습니다’ 안내가 보입니다.",
                f"근거가 기준에 못 미쳐 <b>{response['response_type']}</b>로 처리했습니다."
                "<br><span class='process-note'>추측해서 문장을 만들지 않습니다.</span>",
            )
        )

    stages.append(
        _stage(
            5,
            "답변 문장이 자연스럽게 다듬어집니다.",
            "검색된 근거 안에서만 설명 수준에 맞게 다시 씁니다."
            "<br><span class='process-note'>준비 중 — 생성 담당 작업이 연결되면 동작합니다.</span>",
            pending=True,
        )
    )
    stages.append(
        _stage(
            6,
            "🔊 ‘안내 듣기’를 누르면 읽어 줍니다.",
            "브라우저에 내장된 음성 합성으로 읽습니다."
            "<br><span class='process-note'>ko-KR · 별도 서버나 음성 파일이 필요 없습니다.</span>",
        )
    )

    st.html(
        '<div class="process-flow">'
        '<div class="process-head"><span>사용자가 보는 것</span><span>실제로 일어난 일</span></div>'
        + "".join(stages)
        + "</div>"
    )


def _render_traceback(contexts: list[dict], used_ids: set[str]) -> None:
    used = [c for c in contexts if c.get("chunk_id") in used_ids] or contexts[:1]
    if not used:
        return

    st.markdown("##### 근거를 원문까지 거슬러 올라가기")
    st.caption("답변에 쓰인 조각이 어디서 왔는지 역순으로 확인합니다.")

    index = _manifest_index()
    for context in used:
        title = context.get("title", "제목 없음")
        with st.expander(f"{title} · {context.get('section', '')}"):
            _render_one_trace(context, index)


def _render_one_trace(context: dict, index: dict) -> None:
    eid = _meta(context, "eid")
    record = index.get(eid, {})
    chunk_id = str(context.get("chunk_id", ""))
    parts = chunk_id.split(":")
    content = context.get("content", "")

    st.markdown("**지금 보고 있는 조각**")
    st.caption(
        f"{len(content):,}자 · section `{context.get('section', '-')}` · "
        f"순번 `{parts[-1] if len(parts) >= 2 else '-'}`"
    )
    st.code(chunk_id, language=None)

    st.markdown("**⬆ 어떻게 잘렸나**")
    max_chars = _meta(context, "chunking_max_chars") or "1500"
    overlap = _meta(context, "chunking_overlap_chars") or "200"
    st.caption(
        f"최대 {max_chars}자, 겹침 {overlap}자로 문단 우선 분할 · "
        f"청킹 버전 `{_meta(context, 'chunking_version') or '-'}`"
    )

    st.markdown("**⬆ 어떻게 정제됐나**")
    st.caption(
        f"HTML·공백 정리 후 정제 지문 `{_meta(context, 'document_fingerprint') or '-'}` · "
        f"임베딩 입력 `{_meta(context, 'embedding_input_version') or '-'}`"
    )

    st.markdown("**⬆ 어떻게 수집됐나**")
    if record:
        st.caption(
            f"{record.get('collected_at', '-')} 수집 · 본문 {record.get('content_length', '-')}자 · "
            f"SHA-256 `{(record.get('checksum') or '-')[:16]}…`"
        )
    else:
        st.caption("이 항목의 수집 기록을 `data/manifest.csv`에서 찾지 못했습니다.")

    st.markdown("**⬆ 원문**")
    meta_bits = [b for b in [_meta(context, "field"), _meta(context, "era"), _meta(context, "primary_type")] if b]
    if meta_bits:
        st.caption(" · ".join(meta_bits))
    source_url = context.get("source_url")
    if source_url:
        st.link_button("한국민족문화대백과사전 원문 보기 ↗", source_url, key=f"trace-{chunk_id}")
