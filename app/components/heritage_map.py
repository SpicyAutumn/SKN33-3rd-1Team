"""탐험 지도를 좌우 대칭 마인드맵으로 그린다.

처음에는 방사형으로 그렸는데 두 가지가 걸렸다. 곡선이 글자 위를 가로질러
지저분해 보였고, 위아래로 몰린 이름을 놓을 자리가 없어 좌우 여백은 비는데
가운데만 빽빽했다.

가운데 유산을 두고 좌우로 가지를 나누면 두 문제가 함께 풀린다. 연결선은
직각으로만 꺾여 글자를 지나가지 않고, 이름은 모두 가로로 놓여 긴 이름도
들어간다. 한글은 한 글자가 글자 크기만큼 넓어서 가로 자리가 넉넉해야 한다.

`st.html`은 SVG를 통째로 걷어낸다. `st.markdown(unsafe_allow_html=True)`는
`<linearGradient>`까지 그대로 남긴다. 그래서 이쪽을 쓴다.

클릭은 SVG가 받지 않는다. `<a href="?…">`로 해 봤더니 주소가 바뀌면서 페이지가
통째로 다시 열려 **세션 상태가 날아갔다.** 그래서 그림만 SVG로 그리고 노드
자리마다 투명한 Streamlit 버튼을 겹친다. 좌표는 여기서 백분율로 넘긴다.
"""

from __future__ import annotations

from html import escape
from typing import Any

# 가지마다 다른 색. 청자 녹색과 단청 색조에서 가져왔다.
BRANCH_COLORS = ("#F0CE87", "#5FC1A0", "#8FCBE0", "#E0A277", "#BFA3D8")

WIDTH = 980
HEIGHT = 680
CENTER_X = WIDTH / 2
CENTER_Y = HEIGHT / 2

ROOT_W, ROOT_H, ROOT_R = 230, 92, 22

# 오른쪽 기준값. 왼쪽은 가운데를 기준으로 뒤집어 쓴다.
SPINE_DX = 140          # 가운데에서 세로 줄기까지
PILL_DX = 230           # 가운데에서 가지 이름 안쪽 끝까지
PILL_W, PILL_H = 150, 38
STEM_DX = 265           # 노드로 내려가는 세로선
DOT_DX = 320            # 노드 점
TEXT_GAP = 15           # 점에서 글자까지

ROW_H = 32              # 노드 한 줄 높이
HEAD_GAP = 40           # 가지 이름에서 첫 노드까지
BRANCH_GAP = 26         # 가지 사이 여백

NODE_FONT = 18
NODE_LIMIT = 9          # 한글 9자면 162. 오른쪽 끝까지 딱 들어간다.
BRANCH_LIMIT = 8


def _shorten(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _elbow(x1: float, y1: float, x2: float, y2: float, radius: float = 12) -> str:
    """직각으로 꺾이는 연결선. 모서리만 둥글린다.

    곡선으로 이으면 선이 글자 위를 지나간다. 직각으로 꺾으면 지나갈 일이 없다.
    """
    if abs(y1 - y2) < 1:
        return f"M{x1:.1f},{y1:.1f} L{x2:.1f},{y2:.1f}"
    sweep_x = 1 if x2 > x1 else -1
    sweep_y = 1 if y2 > y1 else -1
    r = min(radius, abs(y2 - y1) / 2, abs(x2 - x1) / 2)
    return (
        f"M{x1:.1f},{y1:.1f} "
        f"L{x1:.1f},{y2 - r * sweep_y:.1f} "
        f"Q{x1:.1f},{y2:.1f} {x1 + r * sweep_x:.1f},{y2:.1f} "
        f"L{x2:.1f},{y2:.1f}"
    )


def _defs() -> str:
    glows = "".join(
        f'<radialGradient id="glow{i}" cx="50%" cy="50%" r="50%">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity=".5"/>'
        f'<stop offset="100%" stop-color="{color}" stop-opacity="0"/>'
        "</radialGradient>"
        for i, color in enumerate(BRANCH_COLORS)
    )
    return (
        "<defs>"
        '<radialGradient id="rootGlow" cx="50%" cy="50%" r="50%">'
        '<stop offset="0%" stop-color="#F0D89B" stop-opacity=".3"/>'
        '<stop offset="100%" stop-color="#F0D89B" stop-opacity="0"/>'
        "</radialGradient>"
        '<linearGradient id="rootFill" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%" stop-color="#3F947B"/>'
        '<stop offset="100%" stop-color="#256452"/>'
        "</linearGradient>"
        f"{glows}"
        "</defs>"
    )


def _root(title: str) -> str:
    name = _shorten(title, 11)
    size = 38 if len(name) <= 5 else (31 if len(name) <= 8 else 25)
    x = CENTER_X - ROOT_W / 2
    y = CENTER_Y - ROOT_H / 2
    return (
        '<g class="hm-root">'
        f'<ellipse cx="{CENTER_X}" cy="{CENTER_Y}" rx="{ROOT_W:.0f}" ry="{ROOT_H * 1.6:.0f}" '
        'fill="url(#rootGlow)"/>'
        f'<rect class="hm-pulse" x="{x - 10:.0f}" y="{y - 10:.0f}" '
        f'width="{ROOT_W + 20}" height="{ROOT_H + 20}" rx="{ROOT_R + 8}" '
        'fill="none" stroke="#F0D89B" stroke-opacity=".45" stroke-width="1.5"/>'
        f'<rect x="{x:.0f}" y="{y:.0f}" width="{ROOT_W}" height="{ROOT_H}" rx="{ROOT_R}" '
        'fill="url(#rootFill)" stroke="#F0D89B" stroke-width="2.5"/>'
        f'<text x="{CENTER_X}" y="{CENTER_Y + size / 3:.0f}" text-anchor="middle" '
        f'font-size="{size}" font-weight="700" fill="#FBF7EC">{escape(name)}</text>'
        "</g>"
    )


def _split(branches: list[dict[str, Any]]) -> tuple[list[int], list[int]]:
    """가지를 좌우로 나눈다. 노드가 많은 쪽부터 번갈아 붙여 양쪽 높이를 맞춘다."""
    order = sorted(range(len(branches)), key=lambda i: -len(branches[i].get("nodes") or []))
    right: list[int] = []
    left: list[int] = []
    right_rows = left_rows = 0
    for index in order:
        rows = len(branches[index].get("nodes") or [])
        if right_rows <= left_rows:
            right.append(index)
            right_rows += rows
        else:
            left.append(index)
            left_rows += rows
    return sorted(right), sorted(left)


def _side_height(branches: list[dict[str, Any]], indexes: list[int]) -> float:
    if not indexes:
        return 0.0
    total = 0.0
    for index in indexes:
        rows = max(len(branches[index].get("nodes") or []), 1)
        total += HEAD_GAP + rows * ROW_H + BRANCH_GAP
    return total - BRANCH_GAP


def render(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """`(SVG 문자열, 노드 위치 목록)`. 위치는 그림 크기에 대한 백분율이다."""
    branches = payload.get("branches") or []
    if not branches:
        return "", []

    parts = [
        f'<div class="hm-wrap"><svg class="hm-svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'role="img" aria-label="문화유산 연결 지도" preserveAspectRatio="xMidYMid meet">',
        _defs(),
    ]
    hits: list[dict[str, Any]] = []
    right, left = _split(branches)
    delay = 0.0

    for indexes, side in ((right, 1), (left, -1)):
        if not indexes:
            continue
        spine_x = CENTER_X + SPINE_DX * side
        cursor = CENTER_Y - _side_height(branches, indexes) / 2

        for index in indexes:
            branch = branches[index]
            color = BRANCH_COLORS[index % len(BRANCH_COLORS)]
            nodes = branch.get("nodes") or []
            head_y = cursor + PILL_H / 2

            pill_near = CENTER_X + PILL_DX * side
            pill_x = pill_near if side > 0 else pill_near - PILL_W
            stem_x = CENTER_X + STEM_DX * side
            dot_x = CENTER_X + DOT_DX * side

            parts.append(
                f'<g class="hm-branch" style="--d:{delay:.2f}s">'
                f'<path class="hm-stem" d="{_elbow(spine_x, CENTER_Y, pill_near, head_y)}" '
                f'stroke="{color}" stroke-width="2.5" fill="none" stroke-opacity=".55"/>'
                f'<rect x="{pill_x:.1f}" y="{cursor:.1f}" width="{PILL_W}" height="{PILL_H}" '
                f'rx="{PILL_H / 2:.0f}" fill="#12352C" fill-opacity=".92" '
                f'stroke="{color}" stroke-width="1.8"/>'
                f'<text x="{pill_x + PILL_W / 2:.1f}" y="{head_y + 6:.1f}" text-anchor="middle" '
                f'font-size="17" font-weight="700" fill="{color}">'
                f"{escape(_shorten(str(branch.get('title', '')), BRANCH_LIMIT))}</text>"
                "</g>"
            )
            delay += 0.1

            row_y = cursor + HEAD_GAP + ROW_H / 2
            for order, node in enumerate(nodes, start=1):
                label = _shorten(str(node.get("title", "")), NODE_LIMIT)
                hits.append(
                    {
                        "key": f"hm-hit-{index}-{order}",
                        "document_id": str(node.get("document_id", "")),
                        "title": str(node.get("title", "")),
                        "reason": str(node.get("reason", "")),
                        "left": dot_x / WIDTH * 100,
                        "top": row_y / HEIGHT * 100,
                    }
                )
                parts.append(
                    f'<g class="hm-node" style="--d:{delay:.2f}s">'
                    f'<path class="hm-link" d="{_elbow(stem_x, head_y, dot_x, row_y)}" '
                    f'stroke="{color}" stroke-width="1.8" fill="none" stroke-opacity=".4"/>'
                    f'<circle class="hm-halo" cx="{dot_x:.1f}" cy="{row_y:.1f}" r="22" '
                    f'fill="url(#glow{index % len(BRANCH_COLORS)})"/>'
                    f'<circle class="hm-dot" cx="{dot_x:.1f}" cy="{row_y:.1f}" r="7" '
                    f'fill="{color}" stroke="#12352C" stroke-width="2"/>'
                    f'<text class="hm-label" x="{dot_x + TEXT_GAP * side:.1f}" '
                    f'y="{row_y + 6:.1f}" text-anchor="{"start" if side > 0 else "end"}" '
                    f'font-size="{NODE_FONT}" font-weight="600">{escape(label)}</text>'
                    "</g>"
                )
                row_y += ROW_H
                delay += 0.04

            cursor += HEAD_GAP + max(len(nodes), 1) * ROW_H + BRANCH_GAP

    parts.append(_root(str((payload.get("root") or {}).get("title", ""))))
    parts.append("</svg></div>")
    return "".join(parts), hits


def position_css(hits: list[dict[str, Any]]) -> str:
    """노드 자리에 버튼을 올려 두는 규칙. 좌표가 매번 달라 여기서 만든다."""
    rules = "".join(
        f'.st-key-{hit["key"]}{{left:{hit["left"]:.3f}%;top:{hit["top"]:.3f}%;}}'
        for hit in hits
    )
    return f"<style>{rules}</style>"
