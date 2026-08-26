import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const inputPath = resolve(
  scriptDir,
  "../docs/00_topic_selection/01_initial_review/revised_topic_2_3_share.md",
);
const outputPath = resolve(
  scriptDir,
  "../docs/00_topic_selection/01_initial_review/revised_topic_2_3_share.html",
);

const markedModulePath = process.env.REVISED_TOPICS_MARKED_MODULE;
if (!markedModulePath) {
  throw new Error("REVISED_TOPICS_MARKED_MODULE 환경 변수가 필요합니다.");
}

const { marked } = await import(pathToFileURL(markedModulePath).href);
const source = readFileSync(inputPath, "utf8");
const normalizedSource = source.replace(
  /\n<div style="page-break-after: always;"><\/div>\n/g,
  "\n",
);
const parts = normalizedSource.split(/\n(?=# 페이지 \d+\/\d+)/);

if (parts.length !== 8) {
  throw new Error(`예상한 문서 구획은 8개이지만 ${parts.length}개를 찾았습니다.`);
}

const coverMarkdown = parts[0].replace(/^# .*?\r?\n/, "").trim();
const pageIds = [
  "education-overview",
  "education-data",
  "goods-overview",
  "goods-data",
  "visit-overview",
  "visit-data",
  "comparison",
];
const pageLabels = [
  "교육: 개요·핵심 기능",
  "교육: 데이터·MVP",
  "굿즈: 개요·핵심 기능",
  "굿즈: 데이터·MVP",
  "방문 도우미: 개요·기능",
  "방문 도우미: 데이터·MVP",
  "비교·최종 의견",
];

const renderMarkdown = (markdown) => marked.parse(markdown, { gfm: true });
const pageSections = parts
  .slice(1)
  .map(
    (part, index) => `
      <section class="page-card" id="${pageIds[index]}" aria-labelledby="${pageIds[index]}-title">
        <div class="page-accent" aria-hidden="true"></div>
        <div class="page-content">
          ${renderMarkdown(part).replace("<h1>", `<h1 id="${pageIds[index]}-title">`)}
        </div>
      </section>`,
  )
  .join("\n");

const navItems = pageIds
  .map(
    (id, index) => `
          <li>
            <a href="#${id}">
              <span class="nav-number">0${index + 1}</span>
              <span>${pageLabels[index]}</span>
            </a>
          </li>`,
  )
  .join("");

const generatedAt = new Intl.DateTimeFormat("ko-KR", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
}).format(new Date());

const html = `<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="3차 LLM 단위 프로젝트 변경 주제 2건의 서비스 범위, 데이터 수집, 제한요소와 MVP 비교 문서">
  <title>3차 단위 프로젝트 변경 주제 검토안</title>
  <style>
    :root {
      --navy: #14253d;
      --navy-soft: #243a59;
      --teal: #087f79;
      --teal-soft: #dff6f2;
      --gold: #d39a2c;
      --gold-soft: #fff6dd;
      --ink: #172033;
      --muted: #596579;
      --line: #dce3eb;
      --paper: #ffffff;
      --surface: #f4f7fa;
      --danger: #a23b3b;
      --shadow: 0 18px 45px rgba(20, 37, 61, 0.09);
      --radius: 20px;
    }

    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at 7% 3%, rgba(8, 127, 121, 0.11), transparent 24rem),
        radial-gradient(circle at 95% 8%, rgba(211, 154, 44, 0.12), transparent 22rem),
        var(--surface);
      font-family: "Pretendard", "Noto Sans KR", "Malgun Gothic", "Apple SD Gothic Neo", sans-serif;
      font-size: 16px;
      line-height: 1.72;
      word-break: keep-all;
    }

    a { color: #0868a5; text-underline-offset: 3px; }
    a:hover { color: var(--teal); }
    .skip-link {
      position: fixed;
      top: 12px;
      left: 12px;
      z-index: 100;
      padding: 10px 14px;
      border-radius: 10px;
      color: white;
      background: var(--navy);
      transform: translateY(-150%);
    }
    .skip-link:focus { transform: translateY(0); }

    .hero {
      position: relative;
      overflow: hidden;
      color: white;
      background: linear-gradient(135deg, #11243d 0%, #183b52 58%, #087f79 100%);
      border-bottom: 4px solid var(--gold);
    }
    .hero::after {
      content: "";
      position: absolute;
      right: -100px;
      bottom: -190px;
      width: 470px;
      height: 470px;
      border: 70px solid rgba(255, 255, 255, 0.055);
      border-radius: 50%;
    }
    .hero-inner {
      position: relative;
      z-index: 1;
      max-width: 1280px;
      margin: 0 auto;
      padding: 58px 32px 52px;
    }
    .eyebrow {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin: 0 0 15px;
      color: #b9f0e8;
      font-size: 0.86rem;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .eyebrow::before {
      content: "";
      width: 28px;
      height: 3px;
      background: var(--gold);
      border-radius: 99px;
    }
    .hero h1 {
      max-width: 900px;
      margin: 0;
      font-size: clamp(2rem, 4.5vw, 3.45rem);
      line-height: 1.18;
      letter-spacing: -0.045em;
    }
    .hero-copy {
      max-width: 790px;
      margin: 18px 0 0;
      color: #dce8ef;
      font-size: 1.08rem;
    }
    .topic-pills {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 25px;
    }
    .topic-pills span {
      padding: 8px 13px;
      border: 1px solid rgba(255, 255, 255, 0.22);
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.08);
      color: #f7fbfc;
      font-size: 0.9rem;
    }

    .layout {
      display: grid;
      grid-template-columns: 255px minmax(0, 1fr);
      gap: 28px;
      width: min(1380px, calc(100% - 40px));
      margin: 34px auto 72px;
      align-items: start;
    }
    .sidebar {
      position: sticky;
      top: 24px;
      padding: 22px 18px;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.9);
      box-shadow: 0 10px 30px rgba(20, 37, 61, 0.06);
      backdrop-filter: blur(12px);
    }
    .sidebar-title {
      margin: 0 0 13px;
      color: var(--navy);
      font-size: 0.83rem;
      font-weight: 900;
      letter-spacing: 0.09em;
      text-transform: uppercase;
    }
    .sidebar ol { margin: 0; padding: 0; list-style: none; }
    .sidebar li + li { margin-top: 4px; }
    .sidebar a {
      display: grid;
      grid-template-columns: 31px 1fr;
      gap: 9px;
      align-items: center;
      padding: 9px 8px;
      border-radius: 10px;
      color: #33415a;
      font-size: 0.9rem;
      font-weight: 700;
      line-height: 1.35;
      text-decoration: none;
    }
    .sidebar a:hover { color: var(--teal); background: var(--teal-soft); }
    .nav-number {
      display: grid;
      place-items: center;
      width: 27px;
      height: 27px;
      border-radius: 8px;
      color: white;
      background: var(--navy-soft);
      font-size: 0.72rem;
      letter-spacing: 0.03em;
    }
    .print-button {
      width: 100%;
      margin-top: 18px;
      padding: 11px 12px;
      border: 0;
      border-radius: 11px;
      color: white;
      background: var(--teal);
      font: inherit;
      font-size: 0.9rem;
      font-weight: 800;
      cursor: pointer;
    }
    .print-button:hover { background: #066b66; }
    .updated {
      margin: 13px 4px 0;
      color: var(--muted);
      font-size: 0.76rem;
      text-align: center;
    }

    .document { min-width: 0; }
    .cover-card,
    .page-card {
      position: relative;
      overflow: hidden;
      margin: 0 0 28px;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--paper);
      box-shadow: var(--shadow);
    }
    .cover-card { padding: 38px 44px; }
    .cover-card::before {
      content: "PROJECT BRIEF";
      display: inline-block;
      margin-bottom: 16px;
      padding: 5px 10px;
      border-radius: 999px;
      color: var(--teal);
      background: var(--teal-soft);
      font-size: 0.76rem;
      font-weight: 900;
      letter-spacing: 0.08em;
    }
    .page-accent {
      height: 7px;
      background: linear-gradient(90deg, var(--teal), #54b9aa 55%, var(--gold));
    }
    .page-content { padding: 42px 48px 48px; }

    h1, h2, h3, h4 { color: var(--navy); line-height: 1.35; }
    h1 { margin: 0 0 28px; font-size: 1.85rem; letter-spacing: -0.035em; }
    h2 {
      margin: 38px 0 14px;
      padding-bottom: 10px;
      border-bottom: 2px solid #e7edf2;
      font-size: 1.34rem;
      letter-spacing: -0.025em;
    }
    h3 { margin: 26px 0 10px; color: var(--teal); font-size: 1.08rem; }
    h4 { margin: 22px 0 8px; font-size: 1rem; }
    p { margin: 9px 0 16px; }
    strong { color: #10223b; }
    ul, ol { padding-left: 1.35rem; }
    li { margin: 5px 0; }
    li::marker { color: var(--teal); font-weight: 800; }
    hr { height: 1px; margin: 32px 0; border: 0; background: var(--line); }

    blockquote {
      margin: 20px 0;
      padding: 18px 22px;
      border: 0;
      border-left: 5px solid var(--teal);
      border-radius: 0 13px 13px 0;
      background: linear-gradient(90deg, var(--teal-soft), #f7fcfb);
      color: #264758;
    }
    blockquote p:last-child { margin-bottom: 0; }

    table {
      width: 100%;
      margin: 18px 0 26px;
      border-collapse: separate;
      border-spacing: 0;
      border: 1px solid var(--line);
      border-radius: 13px;
      overflow: hidden;
      font-size: 0.92rem;
    }
    th, td {
      padding: 12px 14px;
      border-right: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }
    th:last-child, td:last-child { border-right: 0; }
    tr:last-child td { border-bottom: 0; }
    thead th {
      color: white;
      background: var(--navy-soft);
      font-size: 0.88rem;
    }
    tbody tr:nth-child(even) { background: #f8fafc; }
    tbody tr:hover { background: #eff8f6; }

    pre {
      overflow-x: auto;
      margin: 18px 0 25px;
      padding: 20px 22px;
      border: 1px solid #304866;
      border-radius: 14px;
      color: #e8f1f5;
      background: #17283e;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06);
      line-height: 1.6;
    }
    code {
      padding: 0.12em 0.35em;
      border-radius: 5px;
      color: #875719;
      background: var(--gold-soft);
      font-family: "D2Coding", Consolas, monospace;
      font-size: 0.9em;
    }
    pre code { padding: 0; color: inherit; background: transparent; }
    input[type="checkbox"] { accent-color: var(--teal); transform: translateY(1px); }

    .footer {
      max-width: 900px;
      margin: 0 auto 48px;
      color: var(--muted);
      font-size: 0.84rem;
      text-align: center;
    }

    @media (max-width: 980px) {
      .layout { grid-template-columns: 1fr; width: min(920px, calc(100% - 28px)); }
      .sidebar { position: static; }
      .sidebar ol { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .page-content, .cover-card { padding: 32px 28px 36px; }
    }

    @media (max-width: 640px) {
      body { font-size: 15px; word-break: normal; }
      .hero-inner { padding: 42px 20px 38px; }
      .layout { width: min(100% - 18px, 920px); margin-top: 18px; }
      .sidebar ol { grid-template-columns: 1fr; }
      .page-content, .cover-card { padding: 25px 19px 30px; }
      h1 { font-size: 1.45rem; }
      h2 { font-size: 1.18rem; }
      table { display: block; overflow-x: auto; white-space: normal; }
      th, td { min-width: 125px; padding: 10px; }
    }

    @media print {
      @page { size: A4; margin: 13mm; }
      body { color: #111; background: white; font-size: 10pt; line-height: 1.53; }
      .hero { border: 0; background: var(--navy); print-color-adjust: exact; -webkit-print-color-adjust: exact; }
      .hero-inner { padding: 25mm 18mm; }
      .hero h1 { font-size: 28pt; }
      .layout { display: block; width: auto; margin: 0; }
      .sidebar, .footer { display: none; }
      .cover-card, .page-card {
        overflow: visible;
        margin: 0;
        border: 0;
        border-radius: 0;
        box-shadow: none;
      }
      .cover-card { page-break-after: always; padding: 14mm 10mm; }
      .page-card { page-break-after: always; }
      .page-card:last-child { page-break-after: auto; }
      .page-accent { height: 4px; print-color-adjust: exact; -webkit-print-color-adjust: exact; }
      .page-content { padding: 10mm 8mm; }
      h1 { font-size: 19pt; }
      h2 { margin-top: 7mm; font-size: 14pt; }
      h3 { margin-top: 5mm; font-size: 11.5pt; }
      table { font-size: 8.5pt; break-inside: avoid; }
      th, td { padding: 6px 7px; }
      blockquote, pre { break-inside: avoid; }
      a { color: inherit; text-decoration: none; }
    }
  </style>
</head>
<body>
  <a class="skip-link" href="#main-content">본문으로 바로가기</a>
  <header class="hero" id="top">
    <div class="hero-inner">
      <p class="eyebrow">SKN 33 · LLM Unit Project</p>
      <h1>3차 단위 프로젝트<br>변경 주제 검토안</h1>
      <p class="hero-copy">AI 역사교육 플랫폼, 문화유산 굿즈 의사결정 지원과 시설 방문·여행 계획 도우미의 서비스 범위, 데이터 확보, 구현 구조와 제한요소를 팀 회의용으로 정리했습니다.</p>
      <div class="topic-pills" aria-label="핵심 기술">
        <span>RAG</span><span>Vector DB</span><span>LangChain</span><span>LangGraph</span><span>환각 방지</span><span>B2B2C</span>
      </div>
    </div>
  </header>

  <div class="layout">
    <nav class="sidebar" aria-label="문서 목차">
      <p class="sidebar-title">Document map</p>
      <ol>${navItems}
      </ol>
      <button class="print-button" type="button" onclick="window.print()">인쇄 · PDF 저장</button>
      <p class="updated">문서 생성일 ${generatedAt}</p>
    </nav>

    <main class="document" id="main-content">
      <section class="cover-card" aria-label="문서 소개와 전체 방향">
        ${renderMarkdown(coverMarkdown)}
      </section>
      ${pageSections}
    </main>
  </div>

  <footer class="footer">
    이 문서는 주제 확정 전 검토안입니다. 실제 데이터 이용조건과 API 제공 상태는 개발 착수 시 다시 확인해야 합니다.
  </footer>
</body>
</html>`;

writeFileSync(outputPath, html, "utf8");
console.log(outputPath);
