"""문화유산 탐험 지도.

검색한 유산 하나를 뿌리로 두고, 거기서 뻗어 나가는 다른 유산을 보여 준다.
이름을 누르면 그 유산이 새 뿌리가 되어 지도가 다시 그려진다. 한 번 검색한
사용자가 몰랐던 유산까지 따라가게 하는 것이 이 화면의 목적이다.

이전 판은 그 질문에서 검색된 청크 3개만 재료로 썼다. 이어 붙일 항목이 많아야
둘이라 지도라고 부르기 어려웠다. 연결 재료는 `heritage_graph`가 만든 목록
75,835건과 Pinecone에서 가져온다. 여기서는 보여 주는 일만 한다.
"""

from html import escape

import streamlit as st

import heritage_graph
from components import heritage_map

# 탐험 경로에 남길 최대 칸 수. 넘어가면 앞쪽을 접는다.
TRAIL_LIMIT = 6


def _neighbors():
    """Pinecone 연결은 한 번만 만든다. 앵커 조회 결과도 함께 재사용된다."""
    if "explore_neighbors" not in st.session_state:
        try:
            st.session_state["explore_neighbors"] = heritage_graph.build_neighbors()
        except Exception:  # noqa: BLE001
            # 검색이 막혀도 만든 목록만으로 그릴 수 있는 가지는 남는다.
            st.session_state["explore_neighbors"] = None
    return st.session_state["explore_neighbors"]


def _go(document_id: str, title: str) -> None:
    """그 유산을 새 뿌리로 삼는다. 지나온 길은 남겨 둔다."""
    trail = st.session_state.setdefault("explore_trail", [])
    current = st.session_state.get("explore_root")
    if current and current[0] != document_id:
        trail.append(current)
        del trail[:-TRAIL_LIMIT]
    st.session_state["explore_root"] = (document_id, title)


def _reset_to_search(root) -> None:
    st.session_state["explore_trail"] = []
    st.session_state["explore_root"] = (root.document_id, root.title)


def render() -> None:
    st.subheader("문화유산 탐험 지도")
    st.caption(
        "검색한 유산에서 시작해 연결된 다른 유산으로 옮겨 다닙니다. "
        "이름을 누르면 그 유산이 새 출발점이 되고, 설명과 함께 지도가 다시 그려집니다."
    )
    with st.expander("어떤 기준으로 추천하나요?"):
        st.markdown(
            "\n".join(
                (
                    "- **추천 대상은 문화유산만입니다.** "
                    f"{'·'.join(heritage_graph.HERITAGE_TYPES)} 유형만 올립니다. "
                    "인물·제도·단체·지명·사건은 문화유산을 이해하는 배경이지 "
                    "찾아가 보거나 감상할 대상이 아니라 뺐습니다.",
                    "- **묶음마다 근거가 다릅니다.** "
                    "`딸린 유산`은 이름이 지금 보는 유산으로 시작하는 것, "
                    "`시대`·`종류`는 백과사전이 매긴 분류가 같은 것, "
                    "`지역`은 이름 앞머리가 같은 것, "
                    "`다른 갈래`는 종류는 다른데 원문이 가까운 것입니다.",
                    "- **묶음 안의 순서는 원문이 얼마나 가까운지로 정합니다.** "
                    "질문이 아니라 **지금 보고 있는 유산의 원문**을 기준으로 견줍니다. "
                    "제목만 견주면 `경복궁`이 `계궁`·`양궁`처럼 글자만 닮은 낱말과 붙습니다.",
                    f"- **`{'`·`'.join(heritage_graph.UNKNOWN_VALUES)}` 같은 값으로는 잇지 않습니다.** "
                    "수천 건이 함께 달고 있어 같은 값이라는 사실이 아무것도 설명하지 못합니다.",
                )
            )
        )

    result = st.session_state.get("last_result")
    if not result:
        st.info("질문하기 탭에서 답변을 받은 뒤 탐험 지도를 확인해 주세요.")
        return

    book = heritage_graph.catalog()
    searched = book.resolve(result.get("retrieved_contexts", []), result.get("question", ""))
    if searched is None:
        st.warning("이번 검색 결과와 만든 목록을 연결하지 못했습니다.")
        return

    # 새 질문을 하면 그 결과로 출발점을 되돌린다.
    if st.session_state.get("explore_search") != searched.document_id:
        st.session_state["explore_search"] = searched.document_id
        _reset_to_search(searched)

    root_id, root_title = st.session_state.get(
        "explore_root", (searched.document_id, searched.title)
    )

    _render_trail(searched)

    with st.spinner("연결된 문화유산을 찾고 있습니다…"):
        payload = heritage_graph.build_map(root_id, neighbors=_neighbors())

    if payload is None:
        st.warning(f"`{root_title}`의 연결 정보를 찾지 못했습니다.")
        return

    branches = payload["branches"]
    if branches:
        _render_stage(payload)

    _render_root(payload["root"])

    if not branches:
        st.info("이 유산과 이어지는 항목을 찾지 못했습니다. 뒤로 돌아가 다른 길로 가 보세요.")
        return

    with st.expander("목록으로 보기"):
        for index, branch in enumerate(branches):
            with st.container(key=f"heritage-branch-{index}"):
                _render_branch(branch)


def _render_stage(payload: dict) -> None:
    """지도 그림과 그 위에 겹치는 클릭 영역.

    SVG는 `st.html`이 걷어내므로 마크다운으로 넣는다. 클릭은 SVG가 받지 않고
    같은 자리에 겹쳐 둔 투명한 버튼이 받는다. SVG 안에서 링크로 처리하면
    주소가 바뀌면서 페이지가 다시 열려 세션 상태가 날아간다.
    """
    svg, hits = heritage_map.render(payload)
    if not svg:
        return

    with st.container(key="heritage-stage"):
        st.markdown(svg, unsafe_allow_html=True)
        st.html(heritage_map.position_css(hits))
        for hit in hits:
            with st.container(key=hit["key"]):
                if st.button(
                    " ",
                    key=f"go-{hit['key']}",
                    help=_hover_text(hit),
                ):
                    _go(hit["document_id"], hit["title"])
                    st.rerun()


def _hover_text(hit: dict) -> str:
    """커서를 올렸을 때 뜨는 말풍선.

    이름만 띄우면 갈지 말지 고를 수가 없다. 지도에 있는 이름은 대부분
    처음 보는 것이라, 눌러 봐야 무엇인지 알게 되는 화면이었다. 설명 한 줄을
    먼저 보여 주고, 더 보고 싶으면 누르게 한다.
    """
    lines = [f"**{hit['title']}**"]
    facts = " · ".join(
        v for v in (hit.get("period"), hit.get("field"), hit.get("item_type")) if v
    )
    if facts:
        lines.append(facts)
    if hit.get("summary"):
        lines.append(hit["summary"])
    if hit.get("reason"):
        lines.append(f"_{hit['reason']}_")
    lines.append("눌러서 이 유산으로 옮겨 갑니다.")
    return "\n\n".join(lines)


def _render_trail(searched) -> None:
    """지나온 길. 검색 결과로 돌아가는 길을 항상 열어 둔다."""
    trail = st.session_state.get("explore_trail", [])
    root_id, root_title = st.session_state.get("explore_root", (None, ""))
    if not trail and root_id == searched.document_id:
        return

    steps = [searched.title]
    steps += [title for document_id, title in trail if document_id != searched.document_id]
    st.caption(" → ".join(f"`{step}`" for step in steps) + f" → **{root_title}**")

    columns = st.columns([1, 1, 6])
    if trail and columns[0].button("← 뒤로", use_container_width=True):
        st.session_state["explore_root"] = trail.pop()
        st.rerun()
    if columns[1].button("검색 결과로", use_container_width=True):
        _reset_to_search(searched)
        st.rerun()


def _render_root(root: dict) -> None:
    chips = "".join(
        f'<span class="map-chip"><b>{escape(label)}</b> {escape(value)}</span>'
        for label, value in root["fields"]
    )
    summary = root.get("summary") or ""
    st.html(
        '<div class="map-root">'
        '<p class="map-root-label">지금 보고 있는 문화유산</p>'
        f'<h3>{escape(root["title"])}</h3>'
        + (f'<p class="map-summary">{escape(summary)}</p>' if summary else "")
        + f'<div class="map-chips">{chips}</div>'
        + (
            f'<a class="map-source" href="{escape(root["source_url"])}" target="_blank" '
            'rel="noopener noreferrer">공식 원문 보기 ↗</a>'
            if root.get("source_url")
            else ""
        )
        + "</div>"
    )



def _render_branch(branch: dict) -> None:
    st.html(
        '<div class="map-branch-head">'
        f'<span class="map-branch-title">{escape(branch["title"])}</span>'
        f'<span class="map-branch-note">{escape(branch["note"])}</span>'
        "</div>"
    )

    nodes = branch["nodes"]
    for column, node in zip(st.columns(len(nodes)), nodes, strict=False):
        with column:
            if st.button(
                node["title"],
                key=f"map-{branch['title']}-{node['document_id']}",
                use_container_width=True,
                help=_node_help(node),
            ):
                _go(node["document_id"], node["title"])
                st.rerun()


def _node_help(node: dict) -> str:
    parts = [
        f"{label} {value}"
        for label, value in (
            ("시대", node.get("period")),
            ("분야", node.get("field")),
            ("유형", node.get("item_type")),
        )
        if value
    ]
    return " · ".join(parts) or "추가 정보 없음"
