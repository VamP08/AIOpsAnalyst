# Changelog

## 1.0.1 (2026-10-05)

- A case page's issue text ends on a whole word with an ellipsis. The export cut it at 300
  characters, so two cases stopped mid-word ("...the issue is in Tor").
- Icon links carry a version, so browsers that cached the earlier favicon pick up the logo.
- README: screenshots retaken with the logo and colours; the route diagram is a GIF.
- CI runs on actions v7; the site type-checks with TypeScript 7.

## 1.0.0 (2026-10-04)

First release.

- **Sources:** log files (six Loghub datasets: OpenSSH, Apache, OpenStack, ZooKeeper, Linux,
  Blue Gene/L), GitHub issues, failed GitHub Actions runs and public status pages, all in one
  CloudEvents-shaped envelope with deterministic ids and per-source cursors.
- **Clustering before any model call:** a fingerprint for structured alerts, Drain3 for log
  lines, MinHash LSH then MiniLM embeddings for prose. Cluster ids are content-addressed.
- **Triage:** one structured verdict per cluster (category, severity, confidence) through a
  provider router; every verdict records the prompt version and the model that answered.
- **Gate:** an ordered rule table decides auto, suggest, escalate or abstain; YAML routes send
  each decision to Jira, Slack or a person. Sink writes are idempotent.
- **Ask:** `/api/ask` finds clusters by retrieval and answers counts and dates with SQL, with no
  model call.
- **Measured:** Cohen's kappa 0.631 against labels set by the repositories' own maintainers
  (111 clusters); alert recall 1.00 against the operator labels in the BGL dataset; hit@1 0.80
  on 20 questions written before the retriever ran. Prompt 1.2 was measured and rejected.
- **Site:** a static Astro site over the exported corpus (31,155 events in 905 clusters): the
  five outcomes, case pages, how it works, how it was measured, every cluster, and a live feed
  that triages new issues every six hours.

Known limitation: multi-line events such as kernel stack traces are ingested a line at a time.
