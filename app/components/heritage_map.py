"""탐험 지도를 시계방향 무리로 그린다.

가운데 유산을 두고 가지를 시계방향으로 다섯 자리에 놓는다. 자리마다 가지
이름을 세우고 그 아래로 노드를 줄지어 내린다. 네 귀퉁이까지 쓰므로 화면
여백이 놀지 않는다.

이름은 자르지 않는다. 한글은 한 글자가 글자 크기만큼 넓어서 긴 이름을 한
줄로 두면 화면 밖으로 나간다. 그래서 긴 이름은 두 줄로 접는다. 잘라 버리면
무엇인지 알 수 없어 누를 이유가 사라진다.

앞선 두 판에서 배운 것

- 방사형으로 뻗은 곡선은 글자 위를 가로질러 지저분했다. 연결선은 직각으로만
  꺾는다.
- 글자를 방사형으로 눕히면 아래쪽이 세로로 서서 못 읽는다. 전부 가로로 둔다.
- `st.html`은 SVG를 통째로 걷어낸다. `st.markdown(unsafe_allow_html=True)`는
  `<linearGradient>`까지 남긴다.
- 클릭은 SVG가 받지 않는다. `<a href="?…">`는 주소가 바뀌면서 페이지를 다시
  열어 **세션 상태를 날린다.** 그림만 SVG로 그리고 노드 자리마다 투명한
  Streamlit 버튼을 겹친다. 좌표는 여기서 백분율로 넘긴다.
"""

from __future__ import annotations

import math
from html import escape
from typing import Any

# 가지마다 다른 색. 청자 녹색과 단청 색조에서 가져왔다.
BRANCH_COLORS = ("#F0CE87", "#5FC1A0", "#8FCBE0", "#E0A277", "#BFA3D8")

WIDTH = 1180
HEIGHT = 900
CENTER_X = WIDTH / 2
CENTER_Y = HEIGHT / 2

ROOT_W, ROOT_H, ROOT_R = 250, 100, 24

# 가운데에서 가지 이름까지. 이름이 길어 자리가 모자라면 이 값을 줄인다.
CLUSTER_RX, CLUSTER_RY = 230, 230
TOP_CLUSTER_DY = 130    # 12시 무리는 줄이 위로 뻗으므로 가운데에 바짝 붙인다
TOP_CLUSTER_DX = 0      # 점이 이름 안쪽에 붙으므로 밀지 않아도 된다

PILL_W, PILL_H = 166, 42
ROW_H = 38              # 노드 한 줄
HEAD_GAP = 34           # 가지 이름에서 첫 노드까지
DOT_GAP = 14            # 점에서 글자까지

NODE_FONT = 22          # 이름은 자르지도 접지도 줄이지도 않는다. 한 줄로 길게 쓴다.
BRANCH_FONT = 19
EDGE_MARGIN = 22        # 화면 가장자리에서 띄울 거리

# 12시부터 시계방향으로 다섯 자리. 사람이 시계를 읽는 순서와 같다.
CLUSTER_ANGLES = (-90.0, -18.0, 54.0, 126.0, 198.0)

# 노드 줄이 뻗는 방향. 12시 무리는 위로 올라간다. 아래로 내리면 줄이 그대로
# 가운데 유산을 덮어 버린다. 나머지는 가지 이름 아래로 내려간다.
CLUSTER_GROWS_UP = (True, False, False, False, False)


def label_width(text: str, font: float = 0) -> float:
    """이름이 차지하는 가로 폭. 한글은 한 글자가 글자 크기만큼 넓다."""
    return len(text.strip()) * (font or NODE_FONT)


def _shorten(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _elbow(x1: float, y1: float, x2: float, y2: float, radius: float = 12) -> str:
    """직각으로 꺾이는 연결선. 곡선으로 이으면 글자 위를 지나간다."""
    if abs(y1 - y2) < 1:
        return f"M{x1:.1f},{y1:.1f} L{x2:.1f},{y2:.1f}"
    if abs(x1 - x2) < 1:
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
    size = 42 if len(name) <= 5 else (34 if len(name) <= 8 else 27)
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


def _cluster_spot(angle: float) -> tuple[float, float, str]:
    """가지 자리와 글자 방향. 오른쪽 무리는 오른쪽으로, 왼쪽 무리는 왼쪽으로 쓴다."""
    radians = math.radians(angle)
    cosine = math.cos(radians)
    x = CENTER_X + CLUSTER_RX * cosine
    if abs(cosine) < 0.2:
        # 12시 무리는 줄이 위로 뻗는다. 가운데 유산에 바짝 붙여야 위쪽 다섯 줄이
        # 화면 안에 들어온다. 자리가 모자랄 때 줄일 곳은 이 간격이다.
        #
        # 자리를 오른쪽으로 조금 밀어 다른 무리와 같은 방식으로 쓴다. 가운데
        # 정렬로 두면 점이 이름 한가운데를 뚫고 지나간다.
        return x + TOP_CLUSTER_DX, CENTER_Y - TOP_CLUSTER_DY, "start"
    return x, CENTER_Y + CLUSTER_RY * math.sin(radians), "start" if cosine > 0 else "end"


def _node_text(x: float, y: float, anchor: str, label: str, font: float) -> str:
    return (
        f'<text class="hm-label" x="{x:.1f}" y="{y + font / 3:.1f}" text-anchor="{anchor}" '
        f'font-size="{font:.1f}" font-weight="600">{escape(label)}</text>'
    )


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
    delay = 0.0

    for index, branch in enumerate(branches[: len(CLUSTER_ANGLES)]):
        color = BRANCH_COLORS[index % len(BRANCH_COLORS)]
        nodes = branch.get("nodes") or []
        cx, cy, anchor = _cluster_spot(CLUSTER_ANGLES[index])
        direction = 0 if anchor == "middle" else (1 if anchor == "start" else -1)

        pill_x = cx - PILL_W / 2
        parts.append(
            f'<g class="hm-branch" style="--d:{delay:.2f}s">'
            f'<path class="hm-stem" d="{_elbow(CENTER_X, CENTER_Y, cx, cy)}" '
            f'stroke="{color}" stroke-width="2.5" fill="none" stroke-opacity=".45"/>'
            f'<rect x="{pill_x:.1f}" y="{cy - PILL_H / 2:.1f}" width="{PILL_W}" '
            f'height="{PILL_H}" rx="{PILL_H / 2:.0f}" fill="#12352C" fill-opacity=".92" '
            f'stroke="{color}" stroke-width="1.8"/>'
            f'<text x="{cx:.1f}" y="{cy + 6:.1f}" text-anchor="middle" '
            f'font-size="{BRANCH_FONT}" font-weight="700" fill="{color}">'
            f"{escape(_shorten(str(branch.get('title', '')), 9))}</text>"
            "</g>"
        )
        delay += 0.1

        # 노드는 가지 이름 아래로 줄지어 내린다. 점은 이름 쪽 끝에 붙인다.
        grows_up = CLUSTER_GROWS_UP[index % len(CLUSTER_GROWS_UP)]
        step = -1 if grows_up else 1
        # 점은 가지 이름의 **안쪽** 끝에 붙인다. 바깥쪽에 붙이면 이름이 시작하는
        # 자리가 그만큼 밖으로 밀려 긴 이름이 화면을 벗어난다.
        dot_x = cx - (PILL_W / 2 - 10) * direction
        row_y = cy + step * (HEAD_GAP + ROW_H / 2)
        stem_x = cx
        for order, node in enumerate(nodes, start=1):
            label = str(node.get("title", "")).strip()
            text_x = dot_x + DOT_GAP * direction
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
                f'<path class="hm-link" d="{_elbow(stem_x, cy + step * PILL_H / 2, dot_x, row_y)}" '
                f'stroke="{color}" stroke-width="1.6" fill="none" stroke-opacity=".35"/>'
                f'<circle class="hm-halo" cx="{dot_x:.1f}" cy="{row_y:.1f}" r="22" '
                f'fill="url(#glow{index % len(BRANCH_COLORS)})"/>'
                f'<circle class="hm-dot" cx="{dot_x:.1f}" cy="{row_y:.1f}" r="7" '
                f'fill="{color}" stroke="#12352C" stroke-width="2"/>'
                + _node_text(text_x, row_y, anchor, label, NODE_FONT)
                + "</g>"
            )
            # 두 줄짜리 이름은 아랫줄이 다음 점에 닿지 않도록 한 줄만큼 더 띄운다.
            row_y += step * ROW_H
            delay += 0.04

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
