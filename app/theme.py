"""화면 전체에 적용하는 시각 스타일.

문화유산 주제에 맞춰 청자 계열 녹색을 강조색으로 사용한다.

색 규칙: 배경과 글자색은 Streamlit 테마가 정한 값을 그대로 쓴다.
직접 지정하면 밝은 화면과 어두운 화면 중 한쪽에서 글씨가 묻힌다.
여기서는 강조색과 반투명 층만 얹어 두 화면 모두에서 읽히게 한다.
"""

import streamlit as st


_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Gowun+Batang:wght@400;700&family=Noto+Sans+KR:wght@300;400;500;700;900&display=swap');

:root {
  --heritage-display: "Gowun Batang", "Nanum Myeongjo", serif;
  --heritage-body: "Noto Sans KR", "Malgun Gothic", system-ui, sans-serif;
  --heritage-green: #1F5F4E;
  --heritage-green-bright: #4E9C84;
  --heritage-gold: #A97A1F;

  /* 반투명이라 밝은 배경에서는 옅게, 어두운 배경에서는 은은하게 깔린다. */
  --heritage-tint: rgba(31, 95, 78, .09);
  --heritage-tint-strong: rgba(31, 95, 78, .18);
  --heritage-hairline: rgba(128, 128, 128, .28);
  --heritage-dim: rgba(128, 128, 128, .45);
}

/* ── 머리말 ───────────────────────────────────────── */
.heritage-hero {
  position: relative;
  margin: 0 0 2.2rem;
  padding: 3.6rem 3rem 3.2rem;
  border-radius: 22px;
  overflow: hidden;
  isolation: isolate;
  background:
    radial-gradient(ellipse 55% 90% at 82% -12%, rgba(226, 187, 110, .34), transparent 60%),
    radial-gradient(ellipse 45% 75% at 2% 112%, rgba(120, 202, 173, .26), transparent 58%),
    linear-gradient(126deg, #0C2E25 0%, #17493C 38%, #226352 70%, #2C7C64 100%);
  background-size: 160% 160%, 160% 160%, 200% 200%;
  animation: hero-drift 26s ease-in-out infinite alternate;
  box-shadow:
    0 1px 0 rgba(255, 255, 255, .10) inset,
    0 24px 60px rgba(11, 40, 32, .34);
}
@keyframes hero-drift {
  from { background-position: 0% 0%, 100% 100%, 0% 50%; }
  to   { background-position: 12% 8%, 88% 92%, 100% 50%; }
}
@media (prefers-reduced-motion: reduce) { .heritage-hero { animation: none; } }

/* 전통 창살에서 딴 격자. 아주 옅게 깔아 결만 남긴다. */
.heritage-hero::before {
  content: "";
  position: absolute;
  inset: 0;
  z-index: -1;
  opacity: .17;
  background-image: url("data:image/svg+xml,%3Csvg%20xmlns%3D%27http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%27%20width%3D%2772%27%20height%3D%2772%27%20viewBox%3D%270%200%2072%2072%27%3E%3Cg%20fill%3D%27none%27%20stroke%3D%27%23ffffff%27%20stroke-width%3D%271%27%3E%3Cpath%20d%3D%27M36%200v72M0%2036h72%27%2F%3E%3Cpath%20d%3D%27M0%200l72%2072M72%200L0%2072%27%20stroke-opacity%3D%27.45%27%2F%3E%3Ccircle%20cx%3D%2736%27%20cy%3D%2736%27%20r%3D%2711%27%20stroke-opacity%3D%27.55%27%2F%3E%3C%2Fg%3E%3C%2Fsvg%3E");
  mask-image: radial-gradient(ellipse 78% 120% at 92% 10%, #000 0%, transparent 72%);
}
/* 금빛 아치 장식 */
.heritage-hero::after {
  content: "";
  position: absolute;
  z-index: -1;
  width: 26rem;
  height: 26rem;
  right: -8.5rem;
  bottom: -16rem;
  border-radius: 50%;
  border: 1px solid rgba(226, 187, 110, .34);
  box-shadow:
    0 0 0 3.2rem rgba(255, 255, 255, .045),
    0 0 0 3.3rem rgba(226, 187, 110, .16);
}

.heritage-hero h1 {
  margin: 1rem 0 .9rem;
  font-family: var(--heritage-display);
  font-size: clamp(2.2rem, 4.8vw, 3.6rem);
  font-weight: 700;
  letter-spacing: -.038em;
  line-height: 1.12;
  color: #FFFFFF;
  text-wrap: balance;
  text-shadow: 0 2px 20px rgba(0, 0, 0, .22);
}
.heritage-hero p {
  margin: 0;
  max-width: 38rem;
  color: rgba(255, 255, 255, .86);
  font-size: 1.03rem;
  font-weight: 300;
  line-height: 1.78;
  word-break: keep-all;
}
.heritage-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: .5rem;
  padding: .36rem .95rem;
  border: 1px solid rgba(226, 187, 110, .42);
  border-radius: 999px;
  background: rgba(255, 255, 255, .10);
  backdrop-filter: blur(8px);
  color: rgba(255, 255, 255, .94);
  font-size: .72rem;
  font-weight: 700;
  letter-spacing: .13em;
}
.heritage-eyebrow::before {
  content: "";
  width: 5px; height: 5px;
  border-radius: 50%;
  background: #E2BB6E;
  box-shadow: 0 0 0 0 rgba(226, 187, 110, .55);
  animation: eyebrow-pulse 3.2s ease-out infinite;
}
@keyframes eyebrow-pulse {
  0%   { box-shadow: 0 0 0 0 rgba(226, 187, 110, .5); }
  70%  { box-shadow: 0 0 0 9px rgba(226, 187, 110, 0); }
  100% { box-shadow: 0 0 0 0 rgba(226, 187, 110, 0); }
}
@media (prefers-reduced-motion: reduce) { .heritage-eyebrow::before { animation: none; } }

.heritage-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 2.6rem;
  margin-top: 2.4rem;
  padding-top: 1.7rem;
  position: relative;
}
/* 금빛으로 흐려지는 가로선 */
.heritage-stats::before {
  content: "";
  position: absolute;
  top: 0; left: 0;
  width: min(26rem, 100%);
  height: 1px;
  background: linear-gradient(90deg, rgba(226, 187, 110, .8), rgba(255, 255, 255, .16) 55%, transparent);
}
.heritage-stat b {
  display: block;
  font-family: var(--heritage-display);
  font-size: 1.7rem;
  font-weight: 700;
  letter-spacing: -.025em;
  font-variant-numeric: tabular-nums;
  background: linear-gradient(180deg, #FFFFFF 30%, #E2BB6E 190%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.heritage-stat span {
  display: block;
  margin-top: .12rem;
  font-size: .74rem;
  letter-spacing: .07em;
  color: rgba(255, 255, 255, .62);
}

@media (max-width: 720px) {
  .heritage-hero { padding: 2.6rem 1.6rem 2.4rem; border-radius: 18px; }
  .heritage-stats { gap: 1.5rem; }
}

h1, h2, h3, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
  font-family: var(--heritage-display);
  letter-spacing: -.02em;
}
.stTabs [data-baseweb="tab-list"] { gap: .4rem; border-bottom: 0; }
.stTabs [data-baseweb="tab"] {
  padding: .55rem 1.15rem;
  border-radius: 999px;
  border: 1px solid transparent;
  font-weight: 600;
  transition: background .18s ease, border-color .18s ease;
}
.stTabs [data-baseweb="tab"]:hover { background: var(--heritage-tint); }
.stTabs [aria-selected="true"] {
  background: var(--heritage-tint-strong);
  border-color: var(--heritage-green-bright);
}
.stTabs [data-baseweb="tab-highlight"] { display: none; }

/* ── 지표 카드: 테두리만 손대고 글자색은 그대로 둔다 ── */
div[data-testid="stMetric"] {
  padding: .95rem 1.05rem;
  border: 1px solid var(--heritage-hairline);
  border-radius: 12px;
  background: var(--heritage-tint);
}
div[data-testid="stMetricValue"] { font-size: 1.5rem; font-weight: 700; }

/* ── 탐험 지도 ────────────────────────────────────── */
.map-root {
  margin: .2rem 0 1rem;
  padding: 1.1rem 1.3rem;
  border: 1px solid var(--heritage-green-bright);
  border-left: 4px solid var(--heritage-gold);
  border-radius: 14px;
  background: var(--heritage-tint);
}
.map-root { position: relative; }
/* 뿌리 카드 아래로는 첫 가지의 줄기가 32px 올라와 이어 준다.
   카드 쪽에서 따로 선을 내리면 두 선이 어긋난다. */
.map-root h3 { margin: .15rem 0 .6rem; font-family: var(--heritage-display); }
.map-root-label {
  margin: 0;
  font-size: .74rem;
  letter-spacing: .08em;
  text-transform: uppercase;
  opacity: .6;
}
.map-summary { margin: 0 0 .75rem; font-size: .92rem; line-height: 1.6; opacity: .85; }

/* 탐험 지도 — 방사형 별자리.
   SVG는 마크다운으로 넣는다. st.html은 SVG를 통째로 걷어낸다. */
.hm-wrap {
  position: relative;
  margin: 0;
  /* 안쪽 여백을 두면 그림이 무대 안에서 밀려 겹쳐 둔 버튼과 어긋난다. */
  padding: 0;
  border-radius: 20px;
  /* 너무 어두우면 글자가 묻힌다. 청자빛이 남을 만큼만 내린다. */
  background:
    radial-gradient(circle at 50% 45%, rgba(240,216,155,.13), transparent 58%),
    radial-gradient(circle at 50% 50%, #2E6B59 0%, #235445 62%, #1B4437 100%);
  border: 1px solid rgba(240,216,155,.3);
  box-shadow: 0 18px 46px rgba(0,0,0,.22), inset 0 0 120px rgba(0,0,0,.18);
  overflow: hidden;
}
/* 은은하게 도는 빛무리 */
.hm-wrap::before {
  content: "";
  position: absolute;
  inset: -30%;
  background: conic-gradient(from 0deg, transparent 0 78%, rgba(240,216,155,.14) 88%, transparent 100%);
  animation: hm-sweep 22s linear infinite;
  pointer-events: none;
}
/* 그림을 무대에 정확히 채운다.
   `height:100%`는 중간 컨테이너가 auto라서 0으로 풀린다. 절대 배치로 붙인다.
   흐름에 맡기면 SVG가 상자보다 위로 튀어나와 overflow:hidden에 잘린다. */
.hm-svg { position: absolute; inset: 0; display: block; width: 100%; height: 100%; }

/* 그림 위에 클릭 영역을 겹친다.
   무대에 그림과 같은 가로세로 비를 주면 백분율 좌표가 두 축 모두 맞는다.
   `top`의 백분율은 높이를 기준으로 풀리기 때문에 이 비율이 없으면 어긋난다. */
[class*="st-key-heritage-stage"] {
  position: relative;
  aspect-ratio: 1180 / 900;
}
[class*="st-key-heritage-stage"] > div:first-child { position: absolute; inset: 0; }
[class*="st-key-heritage-stage"] .hm-wrap { position: absolute; inset: 0; margin: 0; }
[class*="st-key-hm-hit-"] {
  position: absolute;
  width: 44px;
  height: 44px;
  transform: translate(-50%, -50%);
  z-index: 3;
}
/* 버튼은 보이지 않게 두고 자리만 차지한다. 그림이 이미 점을 그리고 있다.
   `help`를 주면 버튼이 툴팁 span 두 겹에 싸이므로 자식 선택자로는 잡히지 않는다. */
[class*="st-key-hm-hit-"] [data-testid="stTooltipIcon"],
[class*="st-key-hm-hit-"] [data-testid="stTooltipHoverTarget"] {
  display: block;
  width: 44px;
  height: 44px;
}
[class*="st-key-hm-hit-"] button {
  width: 44px !important;
  min-width: 44px !important;
  height: 44px !important;
  padding: 0 !important;
  border-radius: 50% !important;
  border: none !important;
  background: transparent !important;
  color: transparent !important;
  box-shadow: none !important;
}
[class*="st-key-hm-hit-"] button:hover,
[class*="st-key-hm-hit-"] button:focus-visible {
  background: rgba(246, 241, 228, .16) !important;
  box-shadow: 0 0 0 2px rgba(226, 187, 110, .6) !important;
}

@keyframes hm-sweep { to { transform: rotate(360deg); } }

/* 가운데 유산 */
.hm-root { animation: hm-appear .8s ease-out both; }
.hm-pulse { transform-origin: center; animation: hm-pulse 3.4s ease-in-out infinite; }
@keyframes hm-pulse {
  0%, 100% { stroke-opacity: .5; transform: scale(1); }
  50%      { stroke-opacity: .12; transform: scale(1.05); }
}
.hm-pulse { transform-origin: center; transform-box: fill-box; }

/* 줄기와 노드가 차례로 그려진다 */
.hm-branch, .hm-node { animation: hm-appear .55s ease-out both; animation-delay: var(--d, 0s); }
@keyframes hm-appear { from { opacity: 0; transform: scale(.9); } to { opacity: 1; transform: none; } }
.hm-branch, .hm-node { transform-origin: 50% 50%; transform-box: fill-box; }

.hm-stem, .hm-link {
  stroke-dasharray: 620;
  stroke-dashoffset: 620;
  animation: hm-draw 1.1s ease-out both;
  animation-delay: var(--d, 0s);
}
@keyframes hm-draw { to { stroke-dashoffset: 0; } }

/* 노드 */
.hm-node { cursor: pointer; }
.hm-label { fill: #F6F2E6; transition: fill .18s ease; }
.hm-dot { transition: r .18s ease, stroke .18s ease; }
.hm-halo { opacity: .35; transition: opacity .22s ease; }
.hm-node:hover .hm-dot, [class*="st-key-hm-hit-"] button:hover ~ * .hm-dot { r: 14; stroke: #FBF7EC; }
.hm-node:hover .hm-halo { opacity: 1; }
.hm-node:hover .hm-label { fill: #FFFFFF; }
.hm-node:hover .hm-link { stroke-opacity: .95; }
.hm-node:focus-visible .hm-dot { r: 11; stroke: #F6F1E4; }

@media (prefers-reduced-motion: reduce) {
  .hm-wrap::before, .hm-pulse { animation: none; }
  .hm-branch, .hm-node, .hm-stem, .hm-link { animation-duration: .01s; }
}

/* 목록 보기 — 선으로 이은 가지.
   그림은 CSS로 그리고 노드는 진짜 Streamlit 버튼으로 둔다. iframe 안에 그리면
   눌러도 재탐색 신호를 보낼 수 없다. */
[class*="st-key-heritage-branch-"] {
  position: relative;
  padding-left: 1.9rem;
  padding-bottom: .5rem;
}
/* 세로 줄기.
   가지 컨테이너 사이에 Streamlit이 16px 간격을 넣으므로 그만큼 늘려서 잇는다.
   그러지 않으면 줄기가 가지마다 토막 난다. */
[class*="st-key-heritage-branch-"]::before {
  content: "";
  position: absolute;
  left: .5rem;
  top: -16px;
  bottom: -16px;
  border-left: 2px solid var(--heritage-green-bright);
}
/* 첫 가지는 뿌리 카드까지 32px 올라가 만난다 */
[class*="st-key-heritage-branch-0"]::before { top: -32px; }
/* 마지막 가지는 제목 높이까지만 내린다. 아래로 더 갈 곳이 없다. */
[class*="st-key-heritage-branch-"]:last-of-type::before {
  bottom: auto;
  height: calc(1rem + 16px);
}
/* 줄기에서 가지 제목으로 가는 팔꿈치 */
[class*="st-key-heritage-branch-"]::after {
  content: "";
  position: absolute;
  left: .5rem;
  top: 1rem;
  width: 1.1rem;
  border-top: 2px solid var(--heritage-green-bright);
}
.map-branch-head { margin: 0 0 .1rem; }
.map-branch-title {
  display: inline-block;
  padding: .18rem .7rem;
  border: 1px solid var(--heritage-green-bright);
  border-radius: 999px;
  background: var(--heritage-tint-strong);
  font-weight: 700;
  font-size: .92rem;
}
.map-branch-note {
  display: block;
  margin: .3rem 0 0;
  font-size: .8rem;
  opacity: .62;
  line-height: 1.5;
}
/* 가지 제목에서 노드로 내려가는 갈래 */
[class*="st-key-heritage-branch-"] [data-testid="stHorizontalBlock"] {
  position: relative;
  margin-top: 1rem;
}
[class*="st-key-heritage-branch-"] [data-testid="stHorizontalBlock"]::before {
  content: "";
  position: absolute;
  top: -.5rem;
  left: 8%;
  right: 8%;
  border-top: 1px dashed var(--heritage-green-bright);
  opacity: .7;
}
[class*="st-key-heritage-branch-"] [data-testid="stColumn"] { position: relative; }
[class*="st-key-heritage-branch-"] [data-testid="stColumn"]::before {
  content: "";
  position: absolute;
  left: 50%;
  top: -.5rem;
  height: .5rem;
  border-left: 1px dashed var(--heritage-green-bright);
  opacity: .7;
}
.map-chips { display: flex; flex-wrap: wrap; gap: .4rem; }
.map-chip {
  padding: .22rem .6rem;
  border: 1px solid var(--heritage-green-bright);
  border-radius: 999px;
  font-size: .78rem;
  background: var(--heritage-tint-strong);
}
.map-chip b { margin-right: .3rem; opacity: .62; font-weight: 600; }
.map-source {
  display: inline-block;
  margin-top: .7rem;
  font-size: .82rem;
  text-decoration: none;
  opacity: .78;
}
.map-source:hover { opacity: 1; text-decoration: underline; }

/* ── 유사도 막대 ──────────────────────────────────── */
.eval-chart {
  margin: .5rem 0 1rem;
  padding: 1rem 1.1rem .6rem;
  border: 1px solid var(--heritage-hairline);
  border-radius: 12px;
  background: var(--heritage-tint);
}
.eval-row {
  display: grid;
  grid-template-columns: 2.6rem minmax(6rem, 1fr) 3.4rem minmax(0, 1.6fr) auto;
  align-items: center;
  gap: .7rem;
  padding: .34rem 0;
  font-size: .84rem;
  color: inherit;
}
.eval-rank { opacity: .72; font-variant-numeric: tabular-nums; font-weight: 600; }
.eval-track {
  position: relative;
  height: 9px;
  border-radius: 999px;
  background: var(--heritage-tint-strong);
  overflow: hidden;
}
.eval-bar {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: var(--heritage-green-bright);
}
.eval-used .eval-bar { background: var(--heritage-green-bright); }
.eval-pass .eval-bar { background: var(--heritage-green-bright); opacity: .55; }
.eval-drop .eval-bar { background: var(--heritage-dim); }
.eval-score { font-variant-numeric: tabular-nums; font-weight: 600; text-align: right; }
.eval-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.eval-drop .eval-title, .eval-drop .eval-score, .eval-drop .eval-rank { opacity: .55; }
.eval-tag {
  padding: .14rem .55rem;
  border-radius: 999px;
  font-size: .69rem;
  font-weight: 700;
  white-space: nowrap;
  border: 1px solid var(--heritage-hairline);
}
.eval-used .eval-tag {
  background: var(--heritage-green-bright);
  border-color: var(--heritage-green-bright);
  color: #0E2A22;
}
.eval-pass .eval-tag { background: var(--heritage-tint-strong); }
.eval-drop .eval-tag { opacity: .7; }
.eval-note { margin: .55rem 0 0; font-size: .74rem; opacity: .7; }

/* ── 공정 흐름 (사용자 | 구현) ────────────────────── */
.process-flow { margin: 1rem 0 1.6rem; }
.process-head {
  display: grid;
  grid-template-columns: 3.4rem minmax(0, 1fr) minmax(0, 1.3fr);
  gap: 1.4rem;
  padding: 0 0 .7rem;
  font-size: .7rem;
  font-weight: 800;
  letter-spacing: .13em;
  text-transform: uppercase;
  opacity: .5;
}
.process-head span:first-child { grid-column: 2; }

.process-stage {
  position: relative;
  display: grid;
  grid-template-columns: 3.4rem minmax(0, 1fr) minmax(0, 1.3fr);
  gap: 1.4rem;
  align-items: start;
  padding: 1.35rem 0;
  animation: process-in .5s ease both;
}
.process-stage:nth-child(2) { animation-delay: .04s; }
.process-stage:nth-child(3) { animation-delay: .10s; }
.process-stage:nth-child(4) { animation-delay: .16s; }
.process-stage:nth-child(5) { animation-delay: .22s; }
.process-stage:nth-child(6) { animation-delay: .28s; }
.process-stage:nth-child(7) { animation-delay: .34s; }

@keyframes process-in {
  from { opacity: 0; transform: translateY(9px); }
  to   { opacity: 1; transform: none; }
}
@media (prefers-reduced-motion: reduce) {
  .process-stage { animation: none; }
}

/* 단계를 잇는 세로선 */
.process-stage::before {
  content: "";
  position: absolute;
  left: 1.7rem;
  top: 3.1rem;
  bottom: -.6rem;
  width: 2px;
  background: linear-gradient(var(--heritage-tint-strong), transparent);
}
.process-stage:last-child::before { display: none; }

.process-index {
  display: grid;
  place-items: center;
  width: 2.15rem;
  height: 2.15rem;
  margin-left: .3rem;
  border-radius: 50%;
  background: var(--heritage-green-bright);
  color: #0B241D;
  font-family: var(--heritage-display);
  font-size: .95rem;
  font-weight: 700;
  box-shadow: 0 0 0 5px var(--heritage-tint);
}
.process-user { padding-top: .18rem; font-size: .9rem; line-height: 1.66; }
.process-system {
  padding: .85rem 1.1rem;
  border-radius: 12px;
  border: 1px solid var(--heritage-hairline);
  background: var(--heritage-tint);
  font-size: .87rem;
  line-height: 1.66;
  transition: transform .18s ease, box-shadow .18s ease;
}
.process-stage:hover .process-system {
  transform: translateY(-2px);
  box-shadow: 0 8px 22px rgba(31, 95, 78, .14);
}
.process-note { display: inline-block; margin-top: .2rem; font-size: .77rem; opacity: .66; }
.process-pending .process-index {
  background: transparent;
  border: 2px dashed var(--heritage-dim);
  color: inherit;
  box-shadow: none;
}
.process-pending .process-system { border-style: dashed; background: transparent; }
.process-pending { opacity: .68; }

@media (max-width: 720px) {
  .process-head { display: none; }
  .process-stage { grid-template-columns: 2.6rem minmax(0, 1fr); gap: .9rem; }
  .process-system { grid-column: 2; margin-top: .6rem; }
  .process-stage::before { left: 1.25rem; }
}


/* ── 출처 카드 ────────────────────────────────────── */
.cite-card {
  display: grid;
  grid-template-columns: 2.5rem minmax(0, 1fr);
  gap: .95rem;
  align-items: center;
  margin: 1rem 0 .35rem;
  padding: .95rem 1.15rem;
  border: 1px solid var(--heritage-hairline);
  border-left: 3px solid var(--heritage-green-bright);
  border-radius: 12px;
  background: var(--heritage-tint);
  animation: cite-in .45s ease both;
  transition: transform .18s ease, box-shadow .18s ease;
}
.cite-card:hover {
  transform: translateX(3px);
  box-shadow: 0 8px 22px rgba(31, 95, 78, .13);
}
@keyframes cite-in {
  from { opacity: 0; transform: translateX(-8px); }
  to   { opacity: 1; transform: none; }
}
@media (prefers-reduced-motion: reduce) { .cite-card { animation: none; } }

.cite-rank {
  display: grid;
  place-items: center;
  width: 2.1rem;
  height: 2.1rem;
  border-radius: 50%;
  background: var(--heritage-green-bright);
  color: #0B241D;
  font-family: var(--heritage-display);
  font-size: 1rem;
  font-weight: 700;
}
.cite-title {
  font-family: var(--heritage-display);
  font-size: 1.12rem;
  font-weight: 700;
  letter-spacing: -.015em;
  line-height: 1.35;
}
.cite-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: .4rem;
  margin-top: .38rem;
  font-size: .76rem;
}
.cite-source { opacity: .68; }
.cite-chip, .cite-score {
  padding: .1rem .5rem;
  border-radius: 999px;
  border: 1px solid var(--heritage-hairline);
  font-weight: 600;
  letter-spacing: .01em;
}
.cite-score {
  background: var(--heritage-tint-strong);
  border-color: transparent;
  font-variant-numeric: tabular-nums;
}

/* ── 유사도 막대 애니메이션 ───────────────────────── */
.eval-bar { animation: bar-grow .7s cubic-bezier(.22,.9,.3,1) both; transform-origin: left center; }
@keyframes bar-grow { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@media (prefers-reduced-motion: reduce) { .eval-bar { animation: none; } }

/* ── 버튼 ─────────────────────────────────────────── */
.stButton > button, .stFormSubmitButton > button, .stLinkButton > a {
  border-radius: 10px;
  font-weight: 600;
  transition: transform .15s ease, box-shadow .15s ease;
}
.stButton > button:hover, .stFormSubmitButton > button:hover, .stLinkButton > a:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 18px rgba(31, 95, 78, .2);
}

/* ── 확장 패널 ────────────────────────────────────── */
details[data-testid="stExpander"] {
  border-radius: 12px;
  border-color: var(--heritage-hairline);
}

div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 12px; }
</style>
"""


def apply() -> None:
    """앱 시작 시 한 번 호출한다."""
    st.html(_CSS)


def hero(title: str, description: str, eyebrow: str, stats: list[tuple[str, str]] | None = None) -> None:
    """상단 머리말 영역. stats는 (값, 설명) 목록."""
    stat_html = ""
    if stats:
        items = "".join(
            f'<div class="heritage-stat"><b>{value}</b><span>{label}</span></div>' for value, label in stats
        )
        stat_html = f'<div class="heritage-stats">{items}</div>'
    st.html(
        f'<div class="heritage-hero">'
        f'<span class="heritage-eyebrow">{eyebrow}</span>'
        f"<h1>{title}</h1>"
        f"<p>{description}</p>"
        f"{stat_html}"
        f"</div>"
    )
