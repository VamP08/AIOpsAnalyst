import httpx
import pytest

from aiops.envelope import Event
from aiops.pipeline import Pipeline
from aiops.sinks.dryrun import DryRunSink
from aiops.store import Store

ROUTES = [
    {"tiers": ["auto"], "categories": ["crash", "error", "performance"],
     "sink": "tickets"},
    {"tiers": ["escalate"], "sink": "chat"},          # no categories = any
]


def make_pipeline(tmp_path):
    return Pipeline(Store(str(tmp_path / "db.sqlite")), sources=[],
                    routes=ROUTES)


def seed(store, cluster_id="log-abc", tier="auto", category="error", size=2):
    events = [Event(id=f"{cluster_id}-e{i}", source="s",
                    type="dev.aiops.log.line", title=f"failed thing {i}",
                    url=f"https://example.com/{i}")
              for i in range(size)]
    store.insert_events(events)
    store.assign_clusters({e.id: cluster_id for e in events},
                          {cluster_id: ("failed thing <*>", "log")})
    store.upsert_verdict(cluster_id, {
        "category": category, "severity": "medium", "summary": "things fail",
        "confidence": 0.93, "evidence": [events[0].id], "tier": tier,
        "model": "test-model", "promptversion": "1.0"})


def test_auto_error_goes_to_the_ticket_sink_with_evidence(tmp_path):
    pipe = make_pipeline(tmp_path)
    seed(pipe.store)
    tickets, chat = DryRunSink(), DryRunSink()

    assert pipe.route({"tickets": tickets, "chat": chat}) == {"tickets": 1}

    [decision] = tickets.sent
    assert chat.sent == []
    assert decision.cluster_id == "log-abc"
    assert decision.category == "error"
    assert decision.size == 2
    assert decision.label == "failed thing <*>"
    assert [e.url for e in decision.evidence] == ["https://example.com/0",
                                                  "https://example.com/1"]


def test_escalate_goes_to_chat_whatever_the_category(tmp_path):
    pipe = make_pipeline(tmp_path)
    seed(pipe.store, tier="escalate", category="question")
    tickets, chat = DryRunSink(), DryRunSink()
    assert pipe.route({"tickets": tickets, "chat": chat}) == {"chat": 1}


@pytest.mark.parametrize("tier", ["suggest", "abstain"])
def test_tiers_without_a_route_emit_nothing(tmp_path, tier):
    pipe = make_pipeline(tmp_path)
    seed(pipe.store, tier=tier)
    tickets, chat = DryRunSink(), DryRunSink()
    assert pipe.route({"tickets": tickets, "chat": chat}) == {}
    assert tickets.sent == [] and chat.sent == []


def test_a_cluster_is_never_sent_to_the_same_sink_twice(tmp_path):
    pipe = make_pipeline(tmp_path)
    seed(pipe.store)
    tickets = DryRunSink()
    assert pipe.route({"tickets": tickets}) == {"tickets": 1}
    assert pipe.route({"tickets": tickets}) == {}
    assert len(tickets.sent) == 1


def test_returned_reference_is_recorded(tmp_path):
    class KeySink(DryRunSink):
        def emit(self, decision):
            super().emit(decision)
            return "AIOPS-7"

    pipe = make_pipeline(tmp_path)
    seed(pipe.store)
    pipe.route({"tickets": KeySink()})
    assert pipe.store.routed("log-abc") == {"tickets": "AIOPS-7"}


def test_a_failing_sink_does_not_block_others_and_is_retried(tmp_path):
    class BoomSink(DryRunSink):
        def emit(self, decision):
            raise httpx.ConnectError("jira unreachable")

    pipe = make_pipeline(tmp_path)
    seed(pipe.store, tier="escalate")           # matches chat only
    seed(pipe.store, cluster_id="log-def")      # matches tickets only
    chat = DryRunSink()

    result = pipe.route({"tickets": BoomSink(), "chat": chat})
    assert result == {"chat": 1, "tickets": "1 failed"}
    assert len(chat.sent) == 1
    assert pipe.store.routed("log-def") == {}   # unrecorded, so it retries

    assert pipe.route({"tickets": DryRunSink(), "chat": chat}) == {"tickets": 1}

def test_route_limit_caps_one_run_and_the_rest_follow_next_run(tmp_path):
    pipe = make_pipeline(tmp_path)
    for n in range(5):
        seed(pipe.store, cluster_id=f'log-{n}')
    tickets = DryRunSink()

    assert pipe.route({'tickets': tickets}, limit=2) == {'tickets': 2}
    assert pipe.route({'tickets': tickets}, limit=2) == {'tickets': 2}
    assert len({d.cluster_id for d in tickets.sent}) == 4   # none resent
    assert pipe.route({'tickets': tickets}) == {'tickets': 1}
    assert len(tickets.sent) == 5


def test_route_without_a_limit_emits_everything_matching(tmp_path):
    pipe = make_pipeline(tmp_path)
    for n in range(4):
        seed(pipe.store, cluster_id=f'log-{n}')
    tickets = DryRunSink()
    assert pipe.route({'tickets': tickets}) == {'tickets': 4}
