"""탐험 지도를 방사형 SVG로 그린다.

`st.html`은 SVG를 통째로 걷어낸다. `st.markdown(unsafe_allow_html=True)`는
`<linearGradient>`까지 그대로 남긴다. 그래서 이쪽을 쓴다.

클릭은 SVG가 받지 않는다. `<a href="?heritage=…">`로 해 봤더니 주소가 바뀌면서
페이지가 통째로 다시 열려 **세션 상태가 날아갔다.** 질문도 답변도 사라진다.
`st.components`의 iframe도 sandbox에 `allow-top-navigation`이 없어 막힌다.

그래서 그림만 SVG로 그리고, 노드 자리마다 **투명한 Streamlit 버튼을 겹친다.**
버튼은 평범한 재실행을 일으키므로 상태가 유지된다. 좌표는 여기서 계산해
백분율로 넘기고, 배치는 `theme.py`의 규칙이 맡는다.
"""

from __future__ import annotations

import math
from html import escape
from typing import Any

# 가지마다 다른 색. 청자 녹색과 단청 색조에서 가져왔다.
BRANCH_COLORS = ("#E2BB6E", "#3E9B7E", "#7FB3C8", "#C98A5E", "#A98CC0")

WIDTH = 1180
HEIGHT = 860
CENTER_X = WIDTH / 2
CENTER_Y = HEIGHT / 2

ROOT_RADIUS = 62
# 원이 아니라 타원으로 편다. 화면이 가로로 넓고, 위아래로 몰리면 글자가 겹친다.
LABEL_RX, LABEL_RY = 210, 140   # 가지 이름
NODE_RX, NODE_RY = 430, 272     # 노드 점
TEXT_OFFSET = 15                # 점에서 글자까지

# 위쪽 12시 방향부터 시계 방향으로 돈다. 사람이 읽는 순서와 같다.
START_ANGLE = -90.0
SECTOR_GAP = 10.0       # 가지 사이 여백(도)


def _polar(angle_deg: float, rx: float, ry: float) -> tuple[float, float]:
    radians = math.radians(angle_deg)
    return CENTER_X + rx * math.cos(radians), CENTER_Y + ry * math.sin(radians)


def _curve(x1: float, y1: float, x2: float, y2: float, bow: float = 0.28) -> str:
    """두 점을 잇는 부드러운 곡선. 중심에서 살짝 부풀려 방사형 느낌을 준다."""
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    cx = mx + (mx - CENTER_X) * bow
    cy = my + (my - CENTER_Y) * bow
    return f"M{x1:.1f},{y1:.1f} Q{cx:.1f},{cy:.1f} {x2:.1f},{y2:.1f}"


def _label_position(angle_deg: float, x: float, y: float, order: int) -> tuple[float, float, str]:
    """글자는 눕히지 않는다. 방사형으로 돌리면 아래쪽 글자가 세로로 서서 못 읽는다.

    좌우로 벌어진 노드는 점 옆에 둔다. 위아래로 몰린 노드는 점 위아래에 두는데,
    그대로 두면 이웃과 가로로 겹치므로 한 칸씩 번갈아 띄운다.
    """
    cosine = math.cos(math.radians(angle_deg))
    if abs(cosine) < 0.42:
        stagger = 18 if order % 2 else 0
        if math.sin(math.radians(angle_deg)) < 0:
            return x, y - TEXT_OFFSET - 6 - stagger, "middle"
        return x, y + TEXT_OFFSET + 12 + stagger, "middle"
    if cosine > 0:
        return x + TEXT_OFFSET, y + 4, "start"
    return x - TEXT_OFFSET, y + 4, "end"


def _shorten(text: str, limit: int = 14) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _defs() -> str:
    stops = "".join(
        f'<radialGradient id="glow{i}" cx="50%" cy="50%" r="50%">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity=".55"/>'
        f'<stop offset="100%" stop-color="{color}" stop-opacity="0"/>'
        "</radialGradient>"
        for i, color in enumerate(BRANCH_COLORS)
    )
    return (
        "<defs>"
        '<radialGradient id="rootGlow" cx="50%" cy="50%" r="50%">'
        '<stop offset="0%" stop-color="#E2BB6E" stop-opacity=".42"/>'
        '<stop offset="60%" stop-color="#1F5F4E" stop-opacity=".18"/>'
        '<stop offset="100%" stop-color="#1F5F4E" stop-opacity="0"/>'
        "</radialGradient>"
        '<linearGradient id="rootFill" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%" stop-color="#2A7A63"/>'
        '<stop offset="100%" stop-color="#17493C"/>'
        "</linearGradient>"
        f"{stops}"
        "</defs>"
    )


def _root(title: str) -> str:
    name = _shorten(title, 10)
    size = 25 if len(name) <= 6 else 20
    return (
        f'<g class="hm-root">'
        f'<circle cx="{CENTER_X}" cy="{CENTER_Y}" r="{ROOT_RADIUS * 2.6:.0f}" fill="url(#rootGlow)"/>'
        f'<circle class="hm-pulse" cx="{CENTER_X}" cy="{CENTER_Y}" r="{ROOT_RADIUS + 14}" '
        f'fill="none" stroke="#E2BB6E" stroke-opacity=".45" stroke-width="1"/>'
        f'<circle cx="{CENTER_X}" cy="{CENTER_Y}" r="{ROOT_RADIUS}" fill="url(#rootFill)" '
        f'stroke="#E2BB6E" stroke-width="2"/>'
        f'<text x="{CENTER_X}" y="{CENTER_Y + size / 3:.0f}" text-anchor="middle" '
        f'font-size="{size}" font-weight="700" fill="#F6F1E4">{escape(name)}</text>'
        "</g>"
    )


def _sector_angles(branch_count: int) -> list[tuple[float, float]]:
    """가지마다 차지할 각도 구간. 가지 사이는 비워 둔다."""
    span = 360.0 / branch_count
    return [
        (START_ANGLE + i * span + SECTOR_GAP / 2, START_ANGLE + (i + 1) * span - SECTOR_GAP / 2)
        for i in range(branch_count)
    ]


def render(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """`(SVG 문자열, 노드 위치 목록)`.

    위치는 그림 크기에 대한 백분율이다. 화면 폭이 달라져도 버튼이 점을 따라간다.
    """
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
    for index, (branch, (start, end)) in enumerate(zip(branches, _sector_angles(len(branches)))):
        color = BRANCH_COLORS[index % len(BRANCH_COLORS)]
        nodes = branch.get("nodes") or []
        middle = (start + end) / 2

        # 가지 이름 — 줄기 중간에 놓는다.
        lx, ly = _polar(middle, LABEL_RX, LABEL_RY)
        title = _shorten(str(branch.get("title", "")), 12)
        parts.append(
            f'<g class="hm-branch" style="--d:{delay:.2f}s">'
            f'<path class="hm-stem" d="{_curve(CENTER_X, CENTER_Y, lx, ly, 0.1)}" '
            f'stroke="{color}" stroke-width="2.5" fill="none" stroke-opacity=".55"/>'
            f'<rect x="{lx - 54:.1f}" y="{ly - 15:.1f}" width="108" height="30" rx="15" '
            f'fill="#0E2B24" fill-opacity=".82" stroke="{color}" stroke-width="1.4"/>'
            f'<text x="{lx:.1f}" y="{ly + 5:.1f}" text-anchor="middle" font-size="14" '
            f'font-weight="700" fill="{color}">{escape(title)}</text>'
            "</g>"
        )
        delay += 0.12

        if not nodes:
            continue

        # 노드는 구간 안에 고르게 편다. 하나뿐이면 가운데 둔다.
        step = (end - start) / (len(nodes) + 1)
        for order, node in enumerate(nodes, start=1):
            angle = start + step * order if len(nodes) > 1 else middle
            nx, ny = _polar(angle, NODE_RX, NODE_RY)
            tx, ty, anchor = _label_position(angle, nx, ny, order)
            label = _shorten(str(node.get("title", "")), 12)
            document_id = str(node.get("document_id", ""))
            hits.append(
                {
                    "key": f"hm-hit-{index}-{order}",
                    "document_id": document_id,
                    "title": str(node.get("title", "")),
                    "reason": str(node.get("reason", "")),
                    "left": nx / WIDTH * 100,
                    "top": ny / HEIGHT * 100,
                }
            )

            parts.append(
                f'<g class="hm-node" style="--d:{delay:.2f}s">'
                f'<path class="hm-link" d="{_curve(lx, ly, nx, ny)}" stroke="{color}" '
                f'stroke-width="1.6" fill="none" stroke-opacity=".38"/>'
                f'<circle class="hm-halo" cx="{nx:.1f}" cy="{ny:.1f}" r="26" '
                f'fill="url(#glow{index % len(BRANCH_COLORS)})"/>'
                f'<circle class="hm-dot" cx="{nx:.1f}" cy="{ny:.1f}" r="7" fill="{color}" '
                f'stroke="#0E2B24" stroke-width="2"/>'
                f'<text class="hm-label" x="{tx:.1f}" y="{ty:.1f}" '
                f'text-anchor="{anchor}" font-size="13.5" font-weight="600">{escape(label)}</text>'
                "</g>"
            )
            delay += 0.045

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
