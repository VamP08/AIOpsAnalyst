import { OUTCOMES, type Outcome } from "../lib/outcomes";
import { KIND_LABEL } from "../lib/describe";
import { dec, n } from "../lib/format";
import type { Kind } from "../lib/data";

export interface Cluster {
  id: string; label: string; kind: Kind; outcome: Outcome; category: string; severity: string;
  summary: string; confidence: number; tier: string; size: number; first: string; last: string;
  samples: { title: string; url: string | null; time: string }[]; ticket: string | null;
}
export interface Filters { outcome?: Outcome; kind?: Kind; category?: string; q?: string }

export function filterClusters(rows: Cluster[], f: Filters): Cluster[] {
  const q = f.q?.trim().toLowerCase();
  return rows.filter((r) =>
    (!f.outcome || r.outcome === f.outcome) &&
    (!f.kind || r.kind === f.kind) &&
    (!f.category || r.category === f.category) &&
    (!q || `${r.label} ${r.summary ?? ""}`.toLowerCase().includes(q)));
}

const PAGE = 100;
const TIER: Record<string, string> = {
  auto: "handled on its own",
  suggest: "drafted, waits for approval",
  escalate: "a person looks first",
  abstain: "not sure, recorded",
};

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function field(label: string, control: HTMLElement, id: string): HTMLElement {
  const wrap = el("div", "field");
  const l = el("label", undefined, label);
  l.htmlFor = id;
  control.id = id;
  wrap.append(l, control);
  return wrap;
}

function select(options: [string, string][], all: string): HTMLSelectElement {
  const s = el("select");
  for (const [value, text] of [["", all], ...options]) {
    const o = el("option", undefined, text);
    o.value = value;
    s.append(o);
  }
  return s;
}

function row(c: Cluster): HTMLElement {
  const d = el("details", "row");
  const s = el("summary");
  const label = el("span", "label", c.label);
  label.title = c.label;
  s.append(
    label,
    el("span", "meta", KIND_LABEL[c.kind] ?? c.kind),
    el("span", "meta", OUTCOMES.find((o) => o.key === c.outcome)?.label ?? c.outcome),
    el("span", "meta", c.category.replace("_", " ")),
    el("span", "size", `${n(c.size)} events`),
  );
  const body = el("div", "body");
  body.append(
    el("p", "sum", c.summary),
    el("p", "conf", `${TIER[c.tier] ?? c.tier} · ${dec(c.confidence)} sure`),
  );
  if (c.ticket) body.append(el("p", "conf", `Ticket ${c.ticket}`));
  if (c.samples.length) {
    const ul = el("ul", "samples");
    for (const sm of c.samples.slice(0, 5)) {
      const li = el("li");
      if (sm.url?.startsWith("https://")) {
        const a = el("a", undefined, sm.title);
        a.href = sm.url;
        li.append(a);
      } else li.textContent = sm.title;
      ul.append(li);
    }
    body.append(ul);
  }
  d.append(s, body);
  return d;
}

export async function mount(root: HTMLElement): Promise<void> {
  root.textContent = "Loading the piles.";
  let rows: Cluster[];
  try {
    const res = await fetch("/data/clusters.json");
    if (!res.ok) throw new Error(String(res.status));
    rows = (await res.json()) as Cluster[];
  } catch {
    root.textContent = "The piles could not be loaded. They are in ";
    const a = el("a", undefined, "/data/clusters.json");
    a.href = "/data/clusters.json";
    root.append(a, ".");
    return;
  }
  rows.sort((a, b) => b.size - a.size);

  const outcome = select(OUTCOMES.map((o) => [o.key, o.label]), "All outcomes");
  const kind = select((Object.keys(KIND_LABEL) as Kind[]).map((k) => [k, KIND_LABEL[k]]), "All sources");
  const category = select([...new Set(rows.map((r) => r.category))].sort().map((c) => [c, c.replace("_", " ")]), "All categories");
  const q = el("input");
  q.type = "search";
  const filters = el("div", "filters");
  filters.append(field("Outcome", outcome, "f-outcome"), field("Source kind", kind, "f-kind"),
    field("Category", category, "f-category"), field("Search", q, "f-q"));
  const count = el("p", "count");
  count.setAttribute("aria-live", "polite");
  const list = el("div", "list");
  const more = el("button", "more", "Show 100 more");
  more.type = "button";

  let matches: Cluster[] = [];
  let shown = 0;
  const draw = () => {
    const next = matches.slice(shown, shown + PAGE);
    list.append(...next.map(row));
    shown += next.length;
    more.hidden = shown >= matches.length;
    count.textContent = `Showing ${n(shown)} of ${n(matches.length)} piles`;
  };
  const apply = () => {
    matches = filterClusters(rows, {
      outcome: (outcome.value || undefined) as Outcome | undefined,
      kind: (kind.value || undefined) as Kind | undefined,
      category: category.value || undefined,
      q: q.value,
    });
    shown = 0;
    list.replaceChildren();
    draw();
  };
  for (const c of [outcome, kind, category]) c.addEventListener("change", apply);
  q.addEventListener("input", apply);
  more.addEventListener("click", draw);

  root.replaceChildren(filters, count, list, more);
  apply();
}
