// No framework: the page is a table, a detail panel and one POST. A build step
// would cost more than it saves here.
//
// Everything rendered below is untrusted. Issue titles and bodies are written
// by whoever opened the issue, and the summaries come from a model reading that
// same text, so a title carrying markup would otherwise become markup here.
// Nodes are built and filled through textContent; nothing is assembled as an
// HTML string, and every URL is checked before it reaches an href.
const $ = (id) => document.getElementById(id);
const api = (path, options) => fetch(path, options).then((r) => {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
});

let clusters = [];
let selected = null;
// "api" when a server is behind this page, "static" when it is the exported
// corpus on a CDN. Everything read-only works either way; the two features
// that genuinely need a server say so rather than failing quietly.
let mode = "api";

const num = (n) => n.toLocaleString("en-US");
const text = (s) => (s ?? "").toString();

const TIERS = new Set(["auto", "suggest", "escalate", "abstain"]);
const TICKET = /^[A-Z][A-Z0-9]*-\d+$/;

function el(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content != null) node.textContent = content;
  return node;
}

function tierTag(tier) {
  return el("span", TIERS.has(tier) ? `tag ${tier}` : "tag", text(tier));
}

function safeUrl(raw) {
  try {
    const url = new URL(raw, window.location.origin);
    return /^https?:$/.test(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function link(href, label) {
  const url = safeUrl(href);
  if (!url) return el("span", null, text(label));
  const anchor = el("a", null, text(label));
  anchor.href = url;
  anchor.target = "_blank";
  anchor.rel = "noopener noreferrer";
  return anchor;
}

function ticketNode(ref) {
  if (!ref) return el("span");
  const base = window.JIRA_BASE || "";
  // a tracker key has a narrow shape; anything else renders as plain text
  return base && TICKET.test(ref)
    ? link(`${base}/browse/${ref}`, ref)
    : el("span", null, text(ref));
}

function renderStats(s) {
  window.JIRA_BASE = s.jira_base || "";
  const cells = [
    ["events ingested", num(s.events)],
    ["clusters", num(s.clusters)],
    ["compression", `${s.compression}x`, "raw events per cluster"],
    ["triaged", num(s.triaged), `of ${num(s.clusters)}`],
    ["auto-routed", num(s.by_tier.auto ?? 0), "tier auto"],
    ["needs a human", num((s.by_tier.escalate ?? 0) + (s.by_tier.suggest ?? 0)),
      "escalate + suggest"],
    ["prompt", s.prompt_version],
  ];
  const strip = $("stats");
  strip.replaceChildren(...cells.map(([key, value, note]) => {
    const stat = el("div", "stat");
    stat.append(el("div", "k", key));
    const line = el("div", "v", value);
    if (note) line.append(el("small", null, ` ${note}`));
    stat.append(line);
    return stat;
  }));
}

function fillOptions(select, values) {
  select.append(...values.filter(Boolean).sort().map((v) => {
    const option = document.createElement("option");
    option.value = v;
    option.textContent = v;
    return option;
  }));
}

function visible() {
  const q = $("q").value.trim().toLowerCase();
  const category = $("category").value;
  const tier = $("tier").value;
  const source = $("source").value;
  const ticketed = $("routed-only").checked;
  return clusters.filter((c) => {
    if (category && c.category !== category) return false;
    if (tier && c.verdict_tier !== tier) return false;
    if (source && c.tier !== source) return false;
    if (ticketed && !Object.keys(c.routed || {}).length) return false;
    if (!q) return true;
    return `${text(c.summary)} ${text(c.label)}`.toLowerCase().includes(q);
  });
}

function renderRows() {
  const rows = visible();
  $("count").textContent = `${num(rows.length)} of ${num(clusters.length)} clusters`;
  const body = document.createElement("tbody");
  body.id = "rows";
  for (const c of rows) {
    const tr = el("tr", `row${selected === c.id ? " on" : ""}`);
    const summary = el("td", "sum", text(c.summary) || "not triaged");
    if (!c.summary) summary.style.color = "var(--faint)";
    summary.append(el("span", "tpl", text(c.label)));
    const tier = el("td");
    if (c.verdict_tier) tier.append(tierTag(c.verdict_tier));
    const ticket = el("td");
    ticket.append(ticketNode(c.routed?.tickets));
    tr.append(
      summary,
      el("td", null, text(c.category)),
      tier,
      el("td", "num conf", c.confidence == null ? "" : c.confidence.toFixed(2)),
      el("td", "num", num(c.size)),
      ticket);
    tr.addEventListener("click", () => select(c.id));
    body.append(tr);
  }
  $("rows").replaceWith(body);
}

function staticCluster(id) {
  const row = clusters.find((c) => c.id === id);
  return {
    ...row,
    verdict: row.category ? {
      category: row.category, severity: row.severity, summary: row.summary,
      confidence: row.confidence, tier: row.verdict_tier, model: row.model,
      promptversion: row.prompt_version,
    } : null,
    events: (row.samples || []).map((e) => ({ title: e.title, data: { url: e.url } })),
  };
}

async function select(id) {
  selected = id;
  renderRows();
  const c = mode === "static" ? staticCluster(id)
    : await api(`/api/clusters/${encodeURIComponent(id)}`);
  const verdict = c.verdict;

  const panel = el("aside");
  panel.id = "detail";
  panel.append(el("h2", null, "cluster"));

  const dl = document.createElement("dl");
  const pair = (key, ...values) => {
    dl.append(el("dt", null, key));
    const dd = el("dd");
    dd.append(...values);
    dl.append(dd);
  };
  const say = (value) => document.createTextNode(value);

  pair("pattern", say(text(c.label)));
  pair("events", say(num(c.size)));
  pair("source", say(text(c.tier)));
  if (verdict) {
    pair("category", say(`${text(verdict.category)} · ${text(verdict.severity)}`));
    pair("confidence", say(`${verdict.confidence.toFixed(2)} → `),
      tierTag(verdict.tier));
    pair("summary", say(text(verdict.summary)));
    pair("model", say(`${text(verdict.model)} · prompt ${text(verdict.promptversion)}`));
  }
  const routed = Object.entries(c.routed || {});
  if (routed.length) {
    const nodes = [];
    for (const [sink, ref] of routed) {
      if (nodes.length) nodes.push(document.createElement("br"));
      nodes.push(say(`${text(sink)}: `), ref ? ticketNode(ref) : say("sent"));
    }
    pair("routed", ...nodes);
  }
  panel.append(dl);

  const evidence = el("div", "evidence");
  evidence.append(el("h2", null,
    `evidence — ${c.events.length} sample${c.events.length === 1 ? "" : "s"}`));
  const list = document.createElement("ul");
  for (const event of c.events) {
    const item = el("li", null, text(event.title));
    const url = event.data?.url;
    if (url) item.append(document.createElement("br"), link(url, url));
    list.append(item);
  }
  evidence.append(list);
  panel.append(evidence);
  $("detail").replaceWith(panel);
}

async function triagePasted() {
  const pasted = $("paste").value.trim();
  if (!pasted) return;
  $("run").disabled = true;
  $("paste-out").textContent = "asking the same prompt the pipeline uses...";
  try {
    const verdict = await api("/api/triage", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text: pasted }),
    });
    $("paste-out").replaceChildren(
      el("strong", null, text(verdict.category)),
      document.createTextNode(` · ${text(verdict.severity)} · confidence `
        + `${verdict.confidence.toFixed(2)} → `),
      tierTag(verdict.tier),
      document.createElement("br"),
      document.createTextNode(text(verdict.summary)),
      document.createElement("br"),
      el("span", "faint",
        `${text(verdict.model)} · prompt ${text(verdict.prompt_version)}`));
  } catch (e) {
    $("paste-out").textContent =
      `no verdict: ${e.message}. Every provider refused or the reply failed `
      + `validation, so nothing is stored — the pipeline treats that as `
      + `untriaged rather than guessing.`;
  } finally {
    $("run").disabled = false;
  }
}

// the same routing the server uses: counting and timing are answered from the
// data, not from prose, and the static build keeps that property by carrying
// each cluster's first, last and event count
const WHEN = /\b(when|since when|what time|how long|start(ed)?|begin|began|first|last seen)\b/i;
const COUNT = /\b(how many|how much|count|number of|total)\b/i;

function classify(question) {
  if (COUNT.test(question)) return "count";
  if (WHEN.test(question)) return "when";
  return "what";
}

// words that say what kind of question this is, not what it is about; they
// must not drive retrieval or every question matches whatever says "error"
const STOPWORDS = new Set([
  "when", "did", "does", "the", "what", "which", "was", "were", "are", "is",
  "how", "many", "much", "count", "number", "total", "of", "in", "on", "to",
  "for", "and", "or", "any", "there", "show", "me", "begin", "began", "start",
  "started", "first", "last", "seen", "happened", "with", "about", "look",
  "looks", "like", "that", "this", "it", "its", "anything", "wrong",
]);

function askStatic(question) {
  const words = (question.toLowerCase().match(/[a-z0-9_]{2,}/g) || [])
    .filter((w) => !STOPWORDS.has(w));
  const scored = clusters.map((c) => {
    const hay = `${text(c.label)} ${text(c.summary)}`.toLowerCase();
    return { c, score: words.filter((w) => hay.includes(w)).length };
  }).filter((s) => s.score > 0).sort((a, b) => b.score - a.score).slice(0, 5);
  const matches = scored.map(({ c }) => ({
    id: c.id, label: c.label, summary: c.summary, tier: c.verdict_tier,
    events: c.size, first: c.first, last: c.last, how: "lexical",
  }));
  if (!matches.length) {
    return { kind: "none", matches: [], answer: "Nothing in the corpus matches that." };
  }
  const kind = classify(question);
  const top = matches[0];
  if (kind === "count") {
    const events = matches.reduce((sum, m) => sum + m.events, 0);
    return { kind, matches,
      answer: `${num(events)} events in ${matches.length} cluster${matches.length === 1 ? "" : "s"}.` };
  }
  if (kind === "when") {
    return { kind, matches,
      answer: `First seen ${text(top.first)}, last seen ${text(top.last)}, ${num(top.events)} events.` };
  }
  return { kind, matches,
    answer: `${matches.length} matching cluster${matches.length === 1 ? "" : "s"}, `
      + `strongest: ${text(top.summary) || text(top.label)}` };
}

async function askCorpus() {
  const question = $("ask").value.trim();
  if (!question) return;
  $("ask-run").disabled = true;
  $("ask-out").textContent = "searching...";
  try {
    const r = mode === "static" ? askStatic(question)
      : await api(`/api/ask?q=${encodeURIComponent(question)}`);
    const out = $("ask-out");
    out.replaceChildren(el("strong", null, text(r.answer)));
    for (const m of r.matches.slice(0, 3)) {
      const row = el("div", null, `${text(m.label)} `);
      row.style.cssText = "margin-top:4px;color:var(--dim)";
      row.append(el("span", "faint", `${m.events} events, ${text(m.how)}`));
      if (m.tier) row.append(document.createTextNode(" "), tierTag(m.tier));
      out.append(row);
    }
    // counting and timing answers come from the data, not from a model
    out.append(el("div", "faint", mode === "static"
      ? "answered from the exported corpus in your browser, no model call"
      : "answered from the store, no model call"));
  } catch (e) {
    $("ask-out").textContent = `no answer: ${e.message}`;
  } finally {
    $("ask-run").disabled = false;
  }
}

function fromExport(row) {
  // the export names the source tier "source" and the verdict tier "tier";
  // the API does the opposite, so one of them has to be translated
  return { ...row, tier: row.source, verdict_tier: row.tier,
           routed: row.ticket ? { tickets: row.ticket } : {} };
}

async function loadCorpus() {
  try {
    const [stats, rows] = await Promise.all([
      api("/api/stats"), api("/api/clusters?limit=2000"),
    ]);
    return { stats, rows };
  } catch {
    mode = "static";
    const [stats, rows] = await Promise.all([
      api("../data/stats.json"), api("../data/clusters.json"),
    ]);
    return { stats, rows: rows.map(fromExport) };
  }
}

function announceStaticMode() {
  const note = el("div", null,
    "Reading the exported corpus: browsing, filtering, evidence and the ask box "
    + "all work here. Triaging your own text needs the pipeline running, which "
    + "is a local step — see the README.");
  note.style.cssText = "padding:8px 20px;border-bottom:1px solid var(--line);"
    + "color:var(--dim);font-size:12px";
  document.querySelector("header").after(note);
  document.querySelector(".paste:last-of-type")?.remove();
}

async function boot() {
  const { stats, rows } = await loadCorpus();
  clusters = rows;
  if (mode === "static") announceStaticMode();
  renderStats(stats);
  fillOptions($("category"), [...new Set(rows.map((r) => r.category))]);
  fillOptions($("tier"), [...new Set(rows.map((r) => r.verdict_tier))]);
  fillOptions($("source"), [...new Set(rows.map((r) => r.tier))]);
  renderRows();
  ["q", "category", "tier", "source", "routed-only"].forEach((id) =>
    $(id).addEventListener("input", renderRows));
  if (mode !== "static") $("run").addEventListener("click", triagePasted);
  $("ask-run").addEventListener("click", askCorpus);
  $("ask").addEventListener("keydown", (e) => {
    if (e.key === "Enter") askCorpus();
  });
}

boot().catch((e) => {
  const banner = el("div", null, `API unreachable: ${e.message}`);
  banner.style.cssText = "padding:16px;color:#f2777a";
  document.body.prepend(banner);
});
