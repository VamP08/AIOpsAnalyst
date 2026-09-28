# AIOpsAnalyst

**[ai-ops-analyst.vercel.app](https://ai-ops-analyst.vercel.app/)** &mdash; a real
incident replayed from its own timestamps, both scorecards, the tickets it filed,
and what it triaged in the last day.

One triage pipeline for every event stream. Server logs, GitHub issues and
alerts go in; deduplicated clusters with a category, a severity, a confidence
and an evidence trail come out, and a policy table decides what happens to each
one - a Jira ticket, a Slack message, or a human.

The open-source tools in this space each own one silo: alert managers cluster
alerts, issue bots label issues, log tools parse logs. The workflow underneath
is the same three steps in all of them, so this builds the workflow once and
makes the sources adapters.

## The part most of these projects skip: a measured number

Triage quality is a claim. Here is the measurement, the ground truth it used,
and the procedure that produced it.

**Against labels applied by the maintainers of the repositories themselves**
(`bug`, `kind/feature`, and similar, on issues from transformers, next.js,
pytorch, langchain, vscode and kubernetes), as of 2026-09-28:

| | |
|---|---|
| clusters compared | 109 |
| raw agreement | 0.807 |
| Cohen's kappa | **0.610** (95% CI 0.467 - 0.746, bootstrap, seeded) |
| defect | precision 0.94, recall 0.82 (n=76) |
| feature_request | precision 0.81, recall 0.78 (n=32) |
| prompt version | 1.1 |
| models that answered | qwen3.8-27b (96), gpt-oss-120b (12), gpt-oss-20b (1) |

Full scorecard: [`eval/scorecard-external.json`](eval/scorecard-external.json).

Why this ground truth rather than self-made labels: nobody on this project chose
those labels, and anyone can open the issue and check. Maintainer vocabularies
do not distinguish "the process died" from "an operation failed", so the
comparison runs on a collapsed taxonomy (`defect` covers crash and error) - that
limitation, the mapping table, the six-class taxonomy used internally, the
annotation procedure and the known biases are written down in
[`eval/CODEBOOK.md`](eval/CODEBOOK.md).

What the interval was for: the first run of this measurement scored kappa 0.749
on 34 pairs. Tripling the set to 109 moved it to 0.610 - inside the earlier
interval, which is exactly the outcome a published interval is supposed to
warn about. The number to quote is the one with the larger sample, and it sits
at the bottom edge of the "substantial" band, so the rubric has work left in it.
The set grows by harvesting more labelled issues, not by labelling more myself.

**Against the alert labels that Lawrence Livermore's operations staff applied to
their own supercomputer logs** (the BGL dataset, published with Oliner and
Stearley, DSN 2007), 80,000 lines:

| | |
|---|---|
| operator-flagged alert lines | 566 |
| alerts surfaced | 566 &mdash; **recall 1.00**, none missed |
| routine lines suppressed as noise | 73,564 of 79,434 (**92.6%**) |
| clusters a responder reads | **22**, down from 80,000 lines |
| incident types preserved | **3 of 3** clusters carrying operator alerts are surfaced |
| line-level precision | 0.088 |
| line-level kappa | 0.151 (95% CI 0.140 - 0.161) |

Full scorecard: [`eval/scorecard-bgl.json`](eval/scorecard-bgl.json).

The two views disagree and the disagreement is the finding. Nothing that the
operators flagged is lost, and the reading pile drops from eighty thousand lines
to twenty-two clusters. Line-level precision is nevertheless 0.088, because
5,870 routine lines sit in clusters this system calls failures - `4,737 x
double-hummer alignment exception`, for one. Those are real failed operations by
this taxonomy and routine events by the operators', who flag hardware and kernel
incidents and ignore recoverable exceptions. That is a taxonomy mismatch rather
than a mistake in either direction, and it is why the cluster view is reported
next to the line view instead of in place of it.

The label never reaches the model: the parser keeps it in the event's attributes
and the prompt is built from the title and body, which a test asserts.

Rules the numbers follow: labels are made blind to the model's verdicts;
agreement is computed before any prompt change; every verdict stores the prompt
version and the model that answered, and a mixed-version comparison is discarded
rather than averaged.

## Deterministic work first, LLM last

```mermaid
flowchart LR
    L[log files] --> N
    G[GitHub issues] --> N
    A[alert webhooks] --> N
    N[one event envelope<br>CloudEvents-shaped] --> C[cluster<br>deterministic]
    C --> T[LLM triage<br>one call per cluster]
    T --> GT[confidence gate<br>deterministic policy]
    GT --> J[Jira]
    GT --> S[Slack]
    GT --> H[human]
```

Clustering runs before any model sees anything, and the model classifies
clusters, never events. On the OpenSSH dataset from Loghub-2.0 that is 638,947
lines to 39 templates: the model reads 39 things instead of 638,947, which is
both the cost argument and the reliability argument.

Measured on that dataset: compression 16,383x, grouping accuracy 0.7067 against
the published ground-truth templates (in line with Drain's published results),
identical output across two runs, 79k lines/second. Reproduce by fetching
the dataset as described in `corpus/README.md`, then
`python eval/bench_loghub.py corpus/data/OpenSSH/OpenSSH_full.log_structured.csv`.

Three clustering tiers, chosen per payload rather than one algorithm everywhere:
a deterministic fingerprint over configured key fields for structured alerts,
Drain3 template mining for log lines, and MinHash LSH followed by MiniLM
embeddings for prose. No UMAP or HDBSCAN: they cluster prose better and they do
not reproduce run to run, and a number that cannot be reproduced is not worth
having.

## The model labels, the rules act

Every verdict carries a confidence, and a deterministic table - not the model -
decides the consequence:

| tier | when | what happens |
|---|---|---|
| auto | confidence >= 0.9 | routed to its sink without asking |
| suggest | confidence >= 0.7 | drafted, waits for a person |
| escalate | low confidence, or any critical severity | a human is told |
| abstain | neither | recorded, nothing sent |

Critical severity escalates regardless of confidence: paging someone is cheap,
a wrong automatic action during an outage is not. Thresholds live in config, and
the routing table is YAML (see [`pipeline.example.yaml`](pipeline.example.yaml)).

Side effects are idempotent. A `(cluster, sink)` pair is recorded only after the
sink reports success, so a sink that is down costs a retry, never a duplicate
ticket.

## Adding a source or a sink

Two methods and a decorator; the core imports no adapter:

```python
@register("github_issues")
class GitHubIssuesSource(Source):
    def fetch(self, cursor: str | None = None) -> Iterator[Event]: ...

@register("jira")
class JiraSink(Sink):
    def emit(self, decision: Decision) -> str | None: ...
```

Adapters own parsing and nothing else. Each source keeps its own cursor, event
ids are deterministic, and inserts are `INSERT OR IGNORE`, so a stateless cron
run behaves like a continuous pipeline: re-reading a file or re-polling an API
inserts nothing twice.

## Running it

```bash
conda create -n aiopsanalyst python=3.12 -y
conda activate aiopsanalyst
pip install -e ".[dev,cluster,embeddings,server]"
cp .env.example .env          # GROQ_API_KEY and GITHUB_TOKEN are enough to start
cp pipeline.example.yaml pipeline.yaml
pytest                        # 158 tests
uvicorn server.app:app        # dashboard on http://127.0.0.1:8000
```

`AIOPS_DB` points the API at a store. LLM providers are tried in order and any
subset works; with no key at all the deterministic half of the pipeline still
runs and clusters are left untriaged rather than guessed at.

## What this is not

It does not take remediation actions on infrastructure, does not ship its own
monitoring, and has no agent loop. Those are deliberate omissions, not a roadmap
slipping: every one of them needs a trust story this project has not earned yet,
and the measured part is the point.

Corpus: two log sources and six repositories. Nothing here is a claim about
production systems in general.
