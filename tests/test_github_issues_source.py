import json

import httpx

from aiops.sources.github_issues import GitHubIssuesSource

ISSUE = {
    "node_id": "I_abc123",
    "number": 42,
    "title": "Crash on empty config",
    "body": "Traceback ...",
    "state": "open",
    "created_at": "2026-09-01T08:00:00Z",
    "updated_at": "2026-09-02T09:30:00Z",
    "html_url": "https://github.com/acme/widget/issues/42",
    "labels": [{"name": "bug"}, {"name": "p1"}],
    "user": {"login": "someuser"},
}

PULL_REQUEST = {**ISSUE, "number": 43, "node_id": "PR_x",
                "pull_request": {"url": "..."}}


def make_source(pages, captured):
    def handler(request):
        captured.append(request)
        return httpx.Response(200, json=pages.pop(0) if pages else [])

    client = httpx.Client(transport=httpx.MockTransport(handler),
                          base_url="https://api.github.com")
    return GitHubIssuesSource(repo="acme/widget", token="tok", client=client)


def test_issues_become_events_with_github_mapping():
    captured = []
    src = make_source([[ISSUE]], captured)
    [e] = list(src.fetch())
    assert e.source == "github://acme/widget"
    assert e.type == "com.github.issue"
    assert e.subject == "42"
    assert e.title == "Crash on empty config"
    assert e.body == "Traceback ..."
    assert e.url == "https://github.com/acme/widget/issues/42"
    assert e.time == "2026-09-02T09:30:00Z"
    assert e.attributes["labels"] == "bug,p1"
    assert e.attributes["state"] == "open"
    assert e.attributes["author"] == "someuser"


def test_event_id_is_stable_for_same_issue_state():
    a = list(make_source([[ISSUE]], []).fetch())[0].id
    b = list(make_source([[ISSUE]], []).fetch())[0].id
    assert a == b
    updated = {**ISSUE, "updated_at": "2026-09-02T10:00:00Z"}
    c = list(make_source([[updated]], []).fetch())[0].id
    assert c != a


def test_pull_requests_are_skipped():
    events = list(make_source([[ISSUE, PULL_REQUEST]], []).fetch())
    assert [e.subject for e in events] == ["42"]


def test_request_carries_auth_and_since_cursor():
    captured = []
    src = make_source([[ISSUE]], captured)
    list(src.fetch(cursor="2026-09-01T00:00:00Z"))
    req = captured[0]
    assert req.headers["Authorization"] == "Bearer tok"
    assert req.url.path == "/repos/acme/widget/issues"
    params = dict(req.url.params)
    assert params["since"] == "2026-09-01T00:00:00Z"
    assert params["state"] == "all"


def test_cursor_advances_to_max_updated_at():
    older = {**ISSUE, "number": 41, "node_id": "I_old",
             "updated_at": "2026-09-01T12:00:00Z"}
    src = make_source([[ISSUE, older]], [])
    list(src.fetch())
    assert src.cursor == "2026-09-02T09:30:00Z"
