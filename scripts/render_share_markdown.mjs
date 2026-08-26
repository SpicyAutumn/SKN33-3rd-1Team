import fs from "node:fs";
import path from "node:path";

const projectRoot = path.resolve(import.meta.dirname, "..");
const docsDir = path.join(
  projectRoot,
  "docs",
  "00_topic_selection",
  "03_post_meeting_reviews",
);
const targets = [
  "post_meeting_topic_1_heritage_travel_docent.md",
  "post_meeting_topic_2_heritage_learning_companion.md",
  "post_meeting_topic_refinement_log.md",
];

const escapeHtml = (value) => value
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");

const slugCounts = new Map();

function slugify(value) {
  const base = value
    .replace(/[`*_]/g, "")
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase() || "section";
  const count = (slugCounts.get(base) || 0) + 1;
  slugCounts.set(base, count);
  return count === 1 ? base : `${base}-${count}`;
}

function inline(value) {
  const codeTokens = [];
  let output = value.replace(/`([^`]+)`/g, (_, code) => {
    const token = `@@CODE${codeTokens.length}@@`;
    codeTokens.push(`<code>${escapeHtml(code)}</code>`);
    return token;
  });
  output = escapeHtml(output);
  output = output.replace(/\[([^\]]+)\]\((https?:\/\/[^)]+|[^)]+)\)/g, (_, label, href) => {
    const external = /^https?:\/\//.test(href);
    return `<a href="${escapeHtml(href)}"${external ? ' target="_blank" rel="noreferrer"' : ""}>${label}</a>`;
  });
  output = output.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  output = output.replace(/@@CODE(\d+)@@/g, (_, index) => codeTokens[Number(index)]);
  return output;
}

function isTableSeparator(line) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

function cells(line) {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}

function renderMarkdown(markdown) {
  slugCounts.clear();
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const html = [];
  const nav = [];
  let index = 0;
  let skippedDocumentTitle = false;

  while (index < lines.length) {
    const line = lines[index];

    if (!line.trim()) {
      index += 1;
      continue;
    }

    if (line.startsWith("```")) {
      const language = line.slice(3).trim();
      const body = [];
      index += 1;
      while (index < lines.length && !lines[index].startsWith("```")) {
        body.push(lines[index]);
        index += 1;
      }
      index += 1;
      html.push(`<pre class="flow${language ? ` language-${escapeHtml(language)}` : ""}"><code>${escapeHtml(body.join("\n"))}</code></pre>`);
      continue;
    }

    if (/^<div\s+style="page-break-after:\s*always;?"\s*><\/div>$/i.test(line.trim())) {
      html.push('<div class="page-break" aria-hidden="true"></div>');
      index += 1;
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      const label = heading[2].trim();
      if (level === 1 && !skippedDocumentTitle) {
        skippedDocumentTitle = true;
        index += 1;
        continue;
      }
      const id = slugify(label);
      const className = level === 1 ? ' class="page-heading"' : "";
      html.push(`<h${level} id="${id}"${className}>${inline(label)}</h${level}>`);
      if (level === 2) nav.push({ id, label: label.replace(/[*`]/g, "") });
      index += 1;
      continue;
    }

    if (/^---+$/.test(line.trim())) {
      html.push("<hr>");
      index += 1;
      continue;
    }

    if (line.trim().startsWith(">")) {
      const quote = [];
      while (index < lines.length && lines[index].trim().startsWith(">")) {
        quote.push(lines[index].trim().replace(/^>\s?/, ""));
        index += 1;
      }
      html.push(`<aside class="callout">${quote.map((item) => `<p>${inline(item)}</p>`).join("")}</aside>`);
      continue;
    }

    if (line.includes("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
      const header = cells(line);
      index += 2;
      const rows = [];
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        rows.push(cells(lines[index]));
        index += 1;
      }
      html.push(`<div class="table-wrap"><table><thead><tr>${header.map((cell) => `<th>${inline(cell)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${header.map((_, cellIndex) => `<td>${inline(row[cellIndex] || "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
      continue;
    }

    if (/^\s*-\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\s*-\s+/.test(lines[index])) {
        let item = lines[index].replace(/^\s*-\s+/, "");
        item = item.replace(/^\[ \]\s*/, '<span class="checkbox" aria-hidden="true"></span>');
        item = item.replace(/^\[x\]\s*/i, '<span class="checkbox checked" aria-hidden="true">✓</span>');
        items.push(`<li>${inline(item).replace(/&lt;span class=&quot;checkbox([^&]*)&quot; aria-hidden=&quot;true&quot;&gt;([✓]?)&lt;\/span&gt;/, '<span class="checkbox$1" aria-hidden="true">$2</span>')}</li>`);
        index += 1;
      }
      html.push(`<ul>${items.join("")}</ul>`);
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\s*\d+\.\s+/.test(lines[index])) {
        items.push(`<li>${inline(lines[index].replace(/^\s*\d+\.\s+/, ""))}</li>`);
        index += 1;
      }
      html.push(`<ol>${items.join("")}</ol>`);
      continue;
    }

    const paragraph = [line.trim()];
    index += 1;
    while (
      index < lines.length &&
      lines[index].trim() &&
      !/^(#{1,6})\s+/.test(lines[index]) &&
      !/^\s*(?:-|\d+\.)\s+/.test(lines[index]) &&
      !lines[index].trim().startsWith(">") &&
      !lines[index].startsWith("```") &&
      !/^---+$/.test(lines[index].trim()) &&
      !(lines[index].includes("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1])) &&
      !/^<div\s+style="page-break-after:/i.test(lines[index].trim())
    ) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    html.push(`<p>${inline(paragraph.join(" "))}</p>`);
  }

  return { body: html.join("\n"), nav };
}

function buildHtml(markdown, filename) {
  const title = markdown.match(/^#\s+(.+)$/m)?.[1]?.trim() || "프로젝트 주제 검토안";
  const subtitle = markdown.match(/^##\s+(.+)$/m)?.[1]?.trim() || "2차 회의 후속 문서";
  const { body, nav } = renderMarkdown(markdown);
  const navItems = nav.map((item, index) => `<li><a href="#${item.id}"><span>${String(index + 1).padStart(2, "0")}</span>${escapeHtml(item.label)}</a></li>`).join("\n");
  const kind = filename.includes("topic_1") ? "결합 주제 보완안" : filename.includes("topic_2") ? "교육 주제 보완안" : "후속 이행 기록";
  const isTopicDocument = filename.includes("topic_1") || filename.includes("topic_2");
  const heroTitle = isTopicDocument ? subtitle : title;
  const heroCopy = isTopicDocument ? `${title} — 팀 공유 및 후속 검토용 독립 문서` : "2차 회의에서 확인한 후속 작업의 순차 이행 및 상태 기록";

  return `<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="${escapeHtml(title)}">
  <title>${escapeHtml(heroTitle)}</title>
  <style>
    :root{--navy:#14253d;--navy2:#24415e;--teal:#087f79;--teal-soft:#e2f5f2;--gold:#d39a2c;--gold-soft:#fff6dc;--ink:#172033;--muted:#5c687b;--line:#dce3eb;--paper:#fff;--surface:#f3f6f9;--danger:#9d3c45;--shadow:0 18px 48px rgba(20,37,61,.10);--radius:20px}
    *{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;color:var(--ink);background:radial-gradient(circle at 8% 2%,rgba(8,127,121,.11),transparent 25rem),radial-gradient(circle at 95% 8%,rgba(211,154,44,.13),transparent 24rem),var(--surface);font-family:"Pretendard","Noto Sans KR","Malgun Gothic","Apple SD Gothic Neo",sans-serif;font-size:16px;line-height:1.72;word-break:keep-all}a{color:#076b9f;text-underline-offset:3px}a:hover{color:var(--teal)}.skip{position:fixed;left:14px;top:10px;z-index:50;padding:9px 13px;border-radius:10px;color:#fff;background:var(--navy);transform:translateY(-160%)}.skip:focus{transform:none}
    .hero{position:relative;overflow:hidden;color:#fff;background:linear-gradient(135deg,#10243d 0%,#183c54 58%,#087f79 100%);border-bottom:4px solid var(--gold)}.hero:after{content:"";position:absolute;right:-110px;bottom:-210px;width:500px;height:500px;border:72px solid rgba(255,255,255,.055);border-radius:50%}.hero-inner{position:relative;z-index:1;width:min(1180px,calc(100% - 44px));margin:auto;padding:56px 0 50px}.eyebrow{display:flex;align-items:center;gap:10px;margin:0 0 14px;color:#bff3ec;font-weight:800;font-size:.86rem;letter-spacing:.09em}.eyebrow:before{content:"";width:30px;height:3px;border-radius:9px;background:var(--gold)}.hero h1{max-width:950px;margin:0;font-size:clamp(2rem,4.2vw,3.4rem);line-height:1.17;letter-spacing:-.045em}.hero p{max-width:900px;margin:18px 0 0;color:#dce9f0;font-size:1.08rem}.chips{display:flex;flex-wrap:wrap;gap:9px;margin-top:22px}.chips span{padding:7px 12px;border:1px solid rgba(255,255,255,.25);border-radius:999px;background:rgba(255,255,255,.08);font-size:.88rem}
    .layout{display:grid;grid-template-columns:250px minmax(0,1fr);gap:28px;width:min(1380px,calc(100% - 40px));margin:34px auto 70px;align-items:start}.sidebar{position:sticky;top:22px;padding:20px 16px;border:1px solid var(--line);border-radius:18px;background:rgba(255,255,255,.93);box-shadow:0 10px 30px rgba(20,37,61,.07);backdrop-filter:blur(12px)}.sidebar h2{margin:0 0 12px;font-size:.8rem;letter-spacing:.1em;color:var(--navy);text-transform:uppercase}.sidebar ol{list-style:none;margin:0;padding:0}.sidebar li+li{margin-top:3px}.sidebar a{display:grid;grid-template-columns:30px 1fr;gap:8px;align-items:center;padding:8px;border-radius:10px;color:#35445b;font-size:.87rem;font-weight:700;line-height:1.35;text-decoration:none}.sidebar a:hover{background:var(--teal-soft);color:var(--teal)}.sidebar a span{display:grid;place-items:center;width:27px;height:27px;border-radius:8px;color:#fff;background:var(--navy2);font-size:.7rem}.actions{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:17px}.actions button,.actions a{display:block;padding:9px 6px;border:1px solid var(--line);border-radius:9px;background:#fff;color:var(--navy);font:inherit;font-size:.78rem;font-weight:800;text-align:center;text-decoration:none;cursor:pointer}.actions button:hover,.actions a:hover{border-color:var(--teal);color:var(--teal)}
    main{min-width:0;padding:36px clamp(24px,4vw,58px) 54px;border:1px solid var(--line);border-radius:var(--radius);background:var(--paper);box-shadow:var(--shadow)}main>hr:first-of-type{margin-top:24px}.page-heading{margin:6px 0 30px;padding:17px 20px;border-left:6px solid var(--gold);border-radius:0 14px 14px 0;background:linear-gradient(90deg,var(--gold-soft),#fff);color:var(--navy);font-size:clamp(1.45rem,2.6vw,2rem);line-height:1.3}h2{margin:48px 0 17px;padding-bottom:10px;border-bottom:2px solid var(--line);color:var(--navy);font-size:1.46rem;line-height:1.35;letter-spacing:-.025em}h3{margin:32px 0 12px;color:var(--teal);font-size:1.18rem}h4{margin:25px 0 9px;color:var(--navy2)}p{margin:10px 0 16px}strong{color:#10243d}code{padding:.15em .4em;border:1px solid #dce7e7;border-radius:6px;background:#f0f7f6;color:#096f69;font-family:Consolas,"D2Coding",monospace;font-size:.9em}ul,ol{margin:10px 0 21px;padding-left:1.45rem}li{margin:6px 0}li::marker{color:var(--teal);font-weight:800}hr{margin:42px 0;border:0;border-top:1px solid var(--line)}
    .callout{margin:20px 0 27px;padding:20px 22px;border:1px solid #bfe1dc;border-left:6px solid var(--teal);border-radius:14px;background:linear-gradient(135deg,var(--teal-soft),#f8fffe)}.callout p{margin:4px 0}.flow{overflow:auto;margin:18px 0 25px;padding:22px 24px;border:1px solid #294a67;border-radius:16px;background:#12263d;color:#eaf4f8;box-shadow:inset 0 1px rgba(255,255,255,.06);line-height:1.65}.flow code{padding:0;border:0;background:none;color:inherit;font-size:.92rem;white-space:pre}.table-wrap{overflow-x:auto;margin:16px 0 29px;border:1px solid var(--line);border-radius:14px;box-shadow:0 7px 20px rgba(20,37,61,.05)}table{width:100%;border-collapse:collapse;min-width:650px;background:#fff}th,td{padding:13px 15px;border-bottom:1px solid var(--line);border-right:1px solid #edf1f5;text-align:left;vertical-align:top}th:last-child,td:last-child{border-right:0}th{color:#fff;background:var(--navy2);font-size:.9rem}tbody tr:nth-child(even){background:#f8fafc}tbody tr:hover{background:#edf8f6}tbody tr:last-child td{border-bottom:0}.checkbox{display:inline-grid;place-items:center;width:1.05rem;height:1.05rem;margin-right:.42rem;border:2px solid #91a0b2;border-radius:4px;vertical-align:-.12rem;color:#fff;background:#fff;font-size:.7rem}.checkbox.checked{border-color:var(--teal);background:var(--teal)}.page-break{height:1px;margin:52px 0 34px;background:linear-gradient(90deg,transparent,var(--line),transparent)}footer{padding:28px 20px;color:var(--muted);text-align:center;font-size:.86rem}
    @media(max-width:920px){.layout{display:block;width:min(100% - 24px,900px)}.sidebar{position:static;margin-bottom:18px}.sidebar ol{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px}main{padding:28px 20px 42px}.hero-inner{width:min(100% - 32px,900px);padding:42px 0 38px}}@media(max-width:600px){body{font-size:15px;word-break:normal}.sidebar ol{display:block}.hero h1{font-size:2rem}.hero p{font-size:1rem}.layout{width:calc(100% - 14px);margin-top:14px}main{padding:22px 15px 35px;border-radius:14px}h2{font-size:1.28rem}.page-heading{font-size:1.28rem}.table-wrap{margin-left:-6px;margin-right:-6px}}
    @media print{@page{size:A4;margin:15mm 13mm}body{background:#fff;font-size:10.3pt}.hero{background:var(--navy)!important;-webkit-print-color-adjust:exact;print-color-adjust:exact}.hero-inner{width:auto;padding:18mm 8mm 13mm}.hero h1{font-size:25pt}.hero:after,.sidebar,footer{display:none}.layout{display:block;width:auto;margin:0}main{padding:0;border:0;box-shadow:none}.page-heading{break-after:avoid;margin-top:6mm}.page-break{break-after:page;height:0;margin:0;background:none}h2,h3{break-after:avoid}.table-wrap,.callout,.flow{break-inside:avoid}.table-wrap{overflow:visible;box-shadow:none}table{min-width:0;font-size:8.6pt}th,td{padding:6px 7px}a{color:inherit;text-decoration:none}}
  </style>
</head>
<body>
  <a class="skip" href="#content">본문 바로가기</a>
  <header class="hero">
    <div class="hero-inner">
      <div class="eyebrow">${escapeHtml(kind)} · 2026.08.26</div>
      <h1>${escapeHtml(heroTitle)}</h1>
      <p>${escapeHtml(heroCopy)}</p>
      <div class="chips"><span>RAG</span><span>Vector DB</span><span>LangChain</span><span>LangGraph</span><span>팀 검토 전</span></div>
    </div>
  </header>
  <div class="layout">
    <aside class="sidebar" aria-label="문서 목차">
      <h2>Contents</h2>
      <ol>${navItems}</ol>
      <div class="actions"><button type="button" onclick="window.print()">인쇄 / PDF</button><a href="#content">맨 위로</a></div>
    </aside>
    <main id="content">${body}</main>
  </div>
  <footer>SKN33 3차 LLM 단위 프로젝트 · 2차 회의 후속 검토자료 · 팀 합의 전</footer>
</body>
</html>\n`;
}

for (const sourceName of targets) {
  const sourcePath = path.join(docsDir, sourceName);
  const markdown = fs.readFileSync(sourcePath, "utf8");
  const outputName = sourceName.replace(/\.md$/i, ".html");
  fs.writeFileSync(path.join(docsDir, outputName), buildHtml(markdown, sourceName), "utf8");
  console.log(`Rendered ${outputName}`);
}
