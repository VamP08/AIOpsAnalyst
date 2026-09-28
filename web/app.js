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

async function select(id) {
  selected = id;
  renderRows();
  const c = await api(`/api/clusters/${encodeURIComponent(id)}`);
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

async function boot() {
  const [stats, rows] = await Promise.all([
    api("/api/stats"), api("/api/clusters?limit=2000"),
  ]);
  clusters = rows;
  renderStats(stats);
  fillOptions($("category"), [...new Set(rows.map((r) => r.category))]);
  fillOptions($("tier"), [...new Set(rows.map((r) => r.verdict_tier))]);
  fillOptions($("source"), [...new Set(rows.map((r) => r.tier))]);
  renderRows();
  ["q", "category", "tier", "source", "routed-only"].forEach((id) =>
    $(id).addEventListener("input", renderRows));
  $("run").addEventListener("click", triagePasted);
}

boot().catch((e) => {
  const banner = el("div", null, `API unreachable: ${e.message}`);
  banner.style.cssText = "padding:16px;color:#f2777a";
  document.body.prepend(banner);
});
