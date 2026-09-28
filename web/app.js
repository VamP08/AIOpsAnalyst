// No framework: the page is a table, a detail panel and one POST. A build step
// would cost more than it saves here.
const $ = (id) => document.getElementById(id);
const api = (path, options) => fetch(path, options).then((r) => {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
});

let clusters = [];
let selected = null;

const num = (n) => n.toLocaleString("en-US");
const text = (s) => (s ?? "").toString();

function renderStats(s) {
  window.JIRA_BASE = s.jira_base || "";
  const cells = [
    ["events ingested", num(s.events)],
    ["clusters", num(s.clusters)],
    ["compression", `${s.compression}x`, "raw events per cluster"],
    ["triaged", `${num(s.triaged)}`, `of ${num(s.clusters)}`],
    ["auto-routed", num(s.by_tier.auto ?? 0), "tier auto"],
    ["needs a human", num((s.by_tier.escalate ?? 0) + (s.by_tier.suggest ?? 0)),
      "escalate + suggest"],
    ["prompt", s.prompt_version],
  ];
  $("stats").innerHTML = cells.map(([k, v, note]) => `
    <div class="stat"><div class="k">${k}</div>
    <div class="v">${v}${note ? ` <small>${note}</small>` : ""}</div></div>`).join("");
}

function fillOptions(select, values) {
  select.append(...values.filter(Boolean).sort().map((v) => {
    const o = document.createElement("option");
    o.value = o.textContent = v;
    return o;
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

function ticketLink(routed) {
  const ref = routed?.tickets;
  if (!ref) return "";
  const base = window.JIRA_BASE || "";
  return base ? `<a href="${base}/browse/${ref}" target="_blank" rel="noopener">${ref}</a>` : ref;
}

function renderRows() {
  const rows = visible();
  $("count").textContent = `${num(rows.length)} of ${num(clusters.length)} clusters`;
  $("rows").innerHTML = rows.map((c) => `
    <tr class="row ${selected === c.id ? "on" : ""}" data-id="${c.id}">
      <td class="sum">${text(c.summary) || "<span style='color:var(--faint)'>not triaged</span>"}
        <span class="tpl">${text(c.label)}</span></td>
      <td>${text(c.category)}</td>
      <td>${c.verdict_tier ? `<span class="tag ${c.verdict_tier}">${c.verdict_tier}</span>` : ""}</td>
      <td class="num conf">${c.confidence == null ? "" : c.confidence.toFixed(2)}</td>
      <td class="num">${num(c.size)}</td>
      <td>${ticketLink(c.routed)}</td>
    </tr>`).join("");
  document.querySelectorAll("tr.row").forEach((tr) =>
    tr.addEventListener("click", () => select(tr.dataset.id)));
}

async function select(id) {
  selected = id;
  renderRows();
  const c = await api(`/api/clusters/${encodeURIComponent(id)}`);
  const v = c.verdict;
  const routed = Object.entries(c.routed || {});
  $("detail").innerHTML = `
    <h2>cluster</h2>
    <dl>
      <dt>pattern</dt><dd>${text(c.label)}</dd>
      <dt>events</dt><dd>${num(c.size)}</dd>
      <dt>source</dt><dd>${text(c.tier)}</dd>
      ${v ? `
      <dt>category</dt><dd>${v.category} &middot; ${v.severity}</dd>
      <dt>confidence</dt><dd>${v.confidence.toFixed(2)} &rarr;
        <span class="tag ${v.tier}">${v.tier}</span></dd>
      <dt>summary</dt><dd>${text(v.summary)}</dd>
      <dt>model</dt><dd>${text(v.model)} &middot; prompt ${text(v.promptversion)}</dd>` : ""}
      ${routed.length ? `<dt>routed</dt><dd>${routed
        .map(([sink, ref]) => `${sink}: ${ticketLink({ tickets: ref }) || ref || "sent"}`)
        .join("<br>")}</dd>` : ""}
    </dl>
    <div class="evidence">
      <h2>evidence &mdash; ${c.events.length} sample${c.events.length === 1 ? "" : "s"}</h2>
      <ul>${c.events.map((e) => `<li>${text(e.title)}${
        e.data?.url ? `<br><a href="${e.data.url}" target="_blank" rel="noopener">${e.data.url}</a>` : ""
      }</li>`).join("")}</ul>
    </div>`;
}

async function triagePasted() {
  const text_ = $("paste").value.trim();
  if (!text_) return;
  $("run").disabled = true;
  $("paste-out").textContent = "asking the same prompt the pipeline uses...";
  try {
    const v = await api("/api/triage", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text: text_ }),
    });
    $("paste-out").innerHTML = `
      <strong>${v.category}</strong> &middot; ${v.severity} &middot;
      confidence ${v.confidence.toFixed(2)} &rarr;
      <span class="tag ${v.tier}">${v.tier}</span><br>
      ${text(v.summary)}<br>
      <span style="color:var(--faint)">${v.model} &middot; prompt ${v.prompt_version}</span>`;
  } catch (e) {
    $("paste-out").textContent =
      `no verdict: ${e.message}. Every provider refused or the reply failed validation, ` +
      `so nothing is stored — the pipeline treats that as untriaged rather than guessing.`;
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
  document.body.insertAdjacentHTML("afterbegin",
    `<div style="padding:16px;color:#f2777a">API unreachable: ${e.message}</div>`);
});
