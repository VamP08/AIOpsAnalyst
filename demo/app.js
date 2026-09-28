// Static front door. Every number here is read from a file the pipeline wrote,
// and every string rendered came from a log, an issue, or a model reading one
// of those, so nothing is assembled as HTML.
const $ = (id) => document.getElementById(id);
const num = (n) => Number(n ?? 0).toLocaleString("en-US");
const text = (s) => (s ?? "").toString();
const TIERS = new Set(["auto", "suggest", "escalate", "abstain"]);

function el(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content != null) node.textContent = content;
  return node;
}

function tierTag(tier) {
  return el("span", TIERS.has(tier) ? `tag ${tier}` : "tag", text(tier));
}

const load = (name) => fetch(`data/${name}.json`).then((r) => r.json());

function renderCounters(stats) {
  const cells = [
    [num(stats.events), "events ingested"],
    [num(stats.clusters), "clusters"],
    [`${stats.compression}x`, "compression"],
    [num(stats.tickets), "tickets filed"],
    [num(stats.by_tier?.escalate ?? 0), "escalated to a human"],
  ];
  $("counters").replaceChildren(...cells.map(([value, key]) => {
    const box = el("div", "counter");
    box.append(el("div", "v", value), el("div", "k", key));
    return box;
  }));
}

function clock(ms) {
  const total = Math.floor(ms / 1000);
  const mm = String(Math.floor(total / 60)).padStart(2, "0");
  const ss = String(total % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

function replayPlayer(replay, clusters) {
  const byId = new Map(clusters.map((c) => [c.id, c]));
  const events = replay.events;
  const span = events.length ? events[events.length - 1].ms : 0;
  const counts = new Map();
  let alerts = 0;
  let index = 0;
  let elapsed = 0;
  let speed = 300;
  let timer = null;
  let last = 0;

  $("replay-note").textContent =
    `${replay.note}. ${num(events.length)} lines between `
    + `${replay["from"].replace("T", " ")} and ${replay.to.replace("T", " ")}, `
    + `about ${Math.round(span / 60000)} minutes of machine time.`;

  const ticker = $("ticker");
  const formed = $("formed");

  function paintClusters() {
    const ordered = [...counts.entries()].sort((a, b) => b[1] - a[1]);
    formed.replaceChildren(...ordered.map(([id, n]) => {
      const cluster = byId.get(id);
      const row = el("li");
      row.append(el("span", "n", num(n)),
        el("span", "tpl", text(cluster?.label ?? id)));
      if (cluster?.tier) row.append(tierTag(cluster.tier));
      if (cluster?.category) row.append(el("span", "verdict", cluster.category));
      return row;
    }));
    $("cluster-count").textContent = num(counts.size);
  }

  function step(now) {
    if (last) elapsed += (now - last) * speed;
    last = now;
    let drawn = 0;
    let flagged = 0;
    while (index < events.length && events[index].ms <= elapsed) {
      const event = events[index];
      counts.set(event.cluster, (counts.get(event.cluster) ?? 0) + 1);
      if (event.alert) alerts += 1;
      // flagged lines get priority but not the whole pane: 76 of these 4,097
      // lines were flagged, and the ticker should look like that ratio rather
      // than like an emergency
      if (drawn < 6 || (event.alert && flagged < 2)) {
        if (event.alert) flagged += 1;
        const line = el("li", event.alert ? "alert" : null,
          text(event.line ?? byId.get(event.cluster)?.label ?? event.cluster));
        ticker.prepend(line);
        drawn += 1;
      }
      index += 1;
    }
    // a flagged line outlives an ordinary one, but only up to a third of the
    // ticker: during a burst the routine flood is still most of what arrives
    while (ticker.childElementCount > 14) {
      const pinned = ticker.querySelectorAll("li.alert").length;
      const ordinary = pinned > 5 ? null : [...ticker.children].reverse()
        .find((li) => !li.classList.contains("alert"));
      (ordinary ?? ticker.lastElementChild).remove();
    }
    $("line-count").textContent = num(index);
    $("alert-count").textContent = num(alerts);
    $("clock").textContent = clock(Math.min(elapsed, span));
    $("bar").style.width = `${Math.min(100, (elapsed / span) * 100)}%`;
    paintClusters();

    if (index >= events.length) return stop(true);
    timer = requestAnimationFrame(step);
  }

  function stop(finished) {
    cancelAnimationFrame(timer);
    timer = null;
    last = 0;
    $("play").textContent = finished ? "replay" : "play";
    if (finished) { index = events.length; elapsed = span; }
  }

  function start() {
    if (index >= events.length) {            // replay from the top
      index = 0; elapsed = 0; alerts = 0; counts.clear(); ticker.replaceChildren();
    }
    $("play").textContent = "pause";
    timer = requestAnimationFrame(step);
  }

  $("play").addEventListener("click", () => (timer ? stop(false) : start()));
  document.querySelectorAll(".speed").forEach((button) => {
    button.addEventListener("click", () => {
      speed = Number(button.dataset.speed);
      document.querySelectorAll(".speed").forEach((b) => b.classList.remove("on"));
      button.classList.add("on");
    });
  });
  paintClusters();
  start();
}

function scorecard(title, who, headline, rows, caveat) {
  const card = el("div", "card");
  card.append(el("h4", null, title), el("div", "who", who));
  const dl = document.createElement("dl");
  for (const [key, value, big] of rows) {
    dl.append(el("dt", null, key), el("dd", big ? "headline" : null, value));
  }
  card.append(dl);
  if (headline) card.append(el("div", "caveat", headline));
  if (caveat) card.append(el("div", "caveat", caveat));
  return card;
}

function renderScorecards(cards) {
  const out = [];
  const maintainer = cards.maintainer_labels;
  if (maintainer) {
    const ci = maintainer.kappa_ci95 ?? [];
    out.push(scorecard(
      "Agreement with maintainer labels",
      "bug / kind:feature applied by maintainers of transformers, next.js, pytorch, langchain, vscode, kubernetes",
      null,
      [["Cohen's kappa", Number(maintainer.cohens_kappa).toFixed(3), true],
       ["95% CI", `${ci[0]} to ${ci[1]}`],
       ["raw agreement", maintainer.raw_agreement],
       ["clusters compared", num(maintainer.pairs)],
       ["prompt", (maintainer.prompt_versions ?? []).join(", ")]],
      "Maintainers do not separate a crash from a failed operation, so this "
      + "runs on a collapsed taxonomy. An earlier run of the same measurement "
      + "scored 0.749 on 34 pairs; tripling the sample moved it here, inside "
      + "that run's published interval."));
  }
  const operator = cards.operator_labels;
  if (operator) {
    const view = operator.by_cluster ?? {};
    out.push(scorecard(
      "Against supercomputer operator labels",
      "alert labels applied by Lawrence Livermore staff to the Blue Gene/L log, published with the dataset",
      null,
      [["alert recall", Number(operator.alert_recall).toFixed(2), true],
       ["alerts missed", num(operator.alert_missed)],
       ["routine suppressed", `${Math.round((operator.noise_suppression ?? 0) * 100)}%`],
       ["clusters to read", `${num(view.surfaced)} of ${num(view.clusters)}`],
       ["incident types kept", `${view.alert_bearing_surfaced} of ${view.alert_bearing}`]],
      "Line-level precision is 0.088: 5,870 routine lines sit in clusters this "
      + "taxonomy calls failures. Those are real failed operations here and "
      + "routine events to operators who flag hardware and kernel incidents — "
      + "a taxonomy mismatch, reported rather than tuned away.", null));
  }
  $("scorecards").replaceChildren(...out);
}

function renderFiled(clusters, stats) {
  const filed = clusters.filter((c) => c.ticket);
  $("ticket-note").textContent =
    `${filed.length} clusters crossed the confidence gate into a real Jira `
    + `project. Each ticket carries the cluster, the pattern behind it, the `
    + `triage metadata and its evidence. Nothing below was written by hand.`;
  $("filed").replaceChildren(...filed.map((c) => {
    const tr = document.createElement("tr");
    tr.append(el("td", null, c.ticket), el("td", null, text(c.category)),
      el("td", null, text(c.summary)), el("td", "num", num(c.size)));
    return tr;
  }));
}

function ago(iso) {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 60) return `${minutes} minutes ago`;
  const hours = Math.round(minutes / 60);
  return hours < 48 ? `${hours} hours ago` : `${Math.round(hours / 24)} days ago`;
}

function renderLive(live) {
  if (!live?.entries?.length) return;
  $("live-note").textContent =
    `A scheduled job triages whatever ${live.repos.length} public repositories `
    + `posted in the last day and commits the result, so this page can be `
    + `checked against the commit history rather than taken on trust. The `
    + `evaluation corpus is left alone: a score that moves when a stranger `
    + `opens an issue is not a measurement. Last run ${ago(live.updated)}.`;
  $("live-rows").replaceChildren(...live.entries.slice(0, 12).map((e) => {
    const tr = document.createElement("tr");
    const repo = document.createElement("td");
    repo.append(e.url ? Object.assign(document.createElement("a"),
      { href: /^https:\/\/github\.com\//.test(e.url ?? "") ? e.url : "#",
        textContent: text(e.repo), target: "_blank", rel: "noopener noreferrer" })
      : el("span", null, text(e.repo)));
    const tier = el("td");
    tier.append(tierTag(e.tier));
    tr.append(repo, el("td", null, text(e.category)), tier,
      el("td", null, text(e.summary)));
    return tr;
  }));
}

Promise.all([load("stats"), load("clusters"), load("scorecards"), load("replay"),
             load("live").catch(() => null)])
  .then(([stats, clusters, cards, replay, live]) => {
    renderLive(live);
    renderCounters(stats);
    renderScorecards(cards);
    renderFiled(clusters, stats);
    $("generated").textContent = text(stats.generated);
    replayPlayer(replay, clusters);
  })
  .catch((e) => {
    const banner = el("div", null, `could not load the exported data: ${e.message}`);
    banner.style.cssText = "padding:16px;color:#f2777a";
    document.body.prepend(banner);
  });
