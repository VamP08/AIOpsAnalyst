import httpx

from aiops.sources.github_actions import GitHubActionsSource

RUN = {
    "id": 36534891183,
    "name": "Component Fixtures",
    "display_title": "fix: memory leak in modalEditorPart (#326885)",
    "head_branch": "main",
    "head_sha": "abc123",
    "event": "push",
    "conclusion": "failure",
    "run_attempt": 1,
    "created_at": "2026-09-29T05:00:00Z",
    "updated_at": "2026-09-29T05:20:00Z",
    "html_url": "https://github.com/acme/widget/actions/runs/36534891183",
}

JOBS = {"total_count": 2, "jobs": [
    {"name": "Screenshots", "conclusion": "failure",
     "steps": [{"name": "Checkout", "conclusion": "success"},
               {"name": "Fail if blocks-ci hashes changed",
                "conclusion": "failure"}]},
    {"name": "Lint", "conclusion": "success", "steps": []},
]}


def make_source(runs, captured=None, jobs=JOBS, **kwargs):
    def handler(request):
        if captured is not None:
            captured.append(request)
        if request.url.path.endswith("/jobs"):
            return httpx.Response(200, json=jobs)
        return httpx.Response(200, json={"total_count": len(runs),
                                         "workflow_runs": runs})

    client = httpx.Client(transport=httpx.MockTransport(handler),
                          base_url="https://api.github.com")
    return GitHubActionsSource(repo="acme/widget", token="tok", client=client,
                               **kwargs)


def test_failed_run_becomes_event_naming_the_failed_step():
    [e] = list(make_source([RUN]).fetch())
    assert e.source == "github://acme/widget/actions"
    assert e.type == "com.github.workflow_run"
    assert e.subject == "36534891183"
    # the title is what repeats across failures, so it is what clusters them
    assert e.title == ("Component Fixtures failed on main: Screenshots / "
                       "Fail if blocks-ci hashes changed")
    assert "fix: memory leak in modalEditorPart" in e.body
    assert e.url == RUN["html_url"]
    assert e.time == "2026-09-29T05:20:00Z"
    assert e.severitynumber == 17
    assert e.attributes["workflow"] == "Component Fixtures"
    assert e.attributes["branch"] == "main"
    assert e.attributes["event"] == "push"


def test_asks_only_for_failures_on_the_branch_since_cursor():
    captured = []
    list(make_source([RUN], captured, branch="main")
         .fetch(cursor="2026-09-15T00:00:00Z"))
    runs = captured[0]
    assert runs.url.path == "/repos/acme/widget/actions/runs"
    assert runs.headers["Authorization"] == "Bearer tok"
    params = dict(runs.url.params)
    assert params["status"] == "failure"
    assert params["branch"] == "main"
    assert params["created"] == ">2026-09-15T00:00:00Z"
    assert captured[1].url.path == \
        "/repos/acme/widget/actions/runs/36534891183/jobs"


def test_cursor_advances_to_latest_created_at():
    later = {**RUN, "id": 2, "created_at": "2026-09-29T09:00:00Z"}
    src = make_source([RUN, later])
    list(src.fetch())
    assert src.cursor == "2026-09-29T09:00:00Z"


def test_run_with_no_failed_step_falls_back_to_the_workflow():
    jobs = {"total_count": 1, "jobs": [
        {"name": "build", "conclusion": "cancelled", "steps": []}]}
    [e] = list(make_source([RUN], jobs=jobs).fetch())
    assert e.title == "Component Fixtures failed on main"


def test_event_id_is_per_attempt():
    a = list(make_source([RUN]).fetch())[0].id
    assert list(make_source([RUN]).fetch())[0].id == a
    retry = {**RUN, "run_attempt": 2}
    assert list(make_source([retry]).fetch())[0].id != a
