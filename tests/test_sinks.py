import base64
import json

import httpx

from aiops.decision import Decision
from aiops.envelope import Event
from aiops.sinks.dryrun import DryRunSink
from aiops.sinks.jira import JiraSink
from aiops.sinks.slack import SlackSink


def make_decision(**overrides):
    fields = dict(
        cluster_id="log-abc123",
        label="Failed password for <*> from <*> port <*> ssh2",
        tier="auto",
        category="error",
        severity="medium",
        summary="Repeated SSH auth failures against root",
        confidence=0.91,
        size=279,
        evidence=[Event(id="e1", source="syslog://labsz/sshd",
                        type="dev.aiops.log.line",
                        title="Failed password for root from 10.0.0.5",
                        url="https://example.com/log/1")],
    )
    fields.update(overrides)
    return Decision(**fields)


def test_dryrun_sink_records_instead_of_sending():
    sink = DryRunSink()
    assert sink.emit(make_decision()) is None
    assert sink.sent[0].cluster_id == "log-abc123"


def test_slack_posts_summary_with_evidence_and_counts():
    sent = {}

    def handler(request):
        sent["url"] = str(request.url)
        sent["body"] = request.read().decode()
        return httpx.Response(200, text="ok")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    SlackSink(webhook="https://hooks.slack.com/services/T/B/X",
              client=client).emit(make_decision())
    assert sent["url"] == "https://hooks.slack.com/services/T/B/X"
    assert "Repeated SSH auth failures against root" in sent["body"]
    assert "error" in sent["body"] and "279" in sent["body"]
    assert "https://example.com/log/1" in sent["body"]


def test_jira_creates_issue_with_v2_plain_description():
    sent = {}

    def handler(request):
        sent["url"] = str(request.url)
        sent["auth"] = request.headers["Authorization"]
        sent["body"] = request.read().decode()
        return httpx.Response(201, json={"key": "AIOPS-42"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sink = JiraSink(base_url="https://acme.atlassian.net", project="AIOPS",
                    email="me@acme.com", token="tok", client=client)
    assert sink.emit(make_decision()) == "AIOPS-42"

    assert sent["url"] == "https://acme.atlassian.net/rest/api/2/issue"
    expected = base64.b64encode(b"me@acme.com:tok").decode()
    assert sent["auth"] == f"Basic {expected}"
    fields = json.loads(sent["body"])["fields"]
    # v2 takes a plain string; v3 would demand Atlassian Document Format
    assert isinstance(fields["description"], str)
    assert fields["project"] == {"key": "AIOPS"}
    assert "Repeated SSH auth failures" in fields["summary"]
    assert "log-abc123" in fields["description"]   # traceable to the cluster
    assert "https://example.com/log/1" in fields["description"]


def test_jira_error_response_raises_rather_than_reporting_success():
    client = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(400, json={"errors": {"project": "bad"}})))
    sink = JiraSink(base_url="https://acme.atlassian.net", project="NOPE",
                   email="me@acme.com", token="tok", client=client)
    try:
        sink.emit(make_decision())
        assert False, "a rejected ticket must not look like a created one"
    except httpx.HTTPStatusError:
        pass


def test_jira_picks_issue_type_from_category():
    from aiops.sinks.jira import JiraSink

    sent = []

    def handler(request):
        sent.append(json.loads(request.read())["fields"]["issuetype"]["name"])
        return httpx.Response(201, json={"key": "AIOPS-1"})

    sink = JiraSink(base_url="https://x.atlassian.net", project="AIOPS",
                    email="e", token="t",
                    client=httpx.Client(transport=httpx.MockTransport(handler)))
    for category in ("crash", "error", "feature_request", "question"):
        sink.emit(make_decision(category=category))
    assert sent == ["Bug", "Bug", "Story", "Task"]


def test_jira_explicit_issue_type_overrides_the_map():
    from aiops.sinks.jira import JiraSink

    sent = []

    def handler(request):
        sent.append(json.loads(request.read())["fields"]["issuetype"]["name"])
        return httpx.Response(201, json={"key": "AIOPS-1"})

    sink = JiraSink(base_url="https://x.atlassian.net", project="AIOPS",
                    email="e", token="t", issue_type="Task",
                    client=httpx.Client(transport=httpx.MockTransport(handler)))
    sink.emit(make_decision(category="crash"))
    assert sent == ["Task"]


def test_evidence_lines_drop_repeats_from_one_template():
    same = [Event(id=f"e{i}", source="s", type="dev.aiops.log.line",
                  title="pam_unix(sshd:auth): check pass; user unknown")
            for i in range(3)]
    decision = make_decision(evidence=same + [
        Event(id="e9", source="s", type="dev.aiops.log.line",
              title="Failed password for root from 10.0.0.5")])
    lines = decision.evidence_lines()
    assert len(lines) == 2
    assert lines[0].endswith("check pass; user unknown")
