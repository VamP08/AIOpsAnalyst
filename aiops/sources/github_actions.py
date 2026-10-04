"""Failed GitHub Actions runs of any public repo as an event stream.

A run on its own says only "CI failed"; which job and which step failed is what
separates a flaky screenshot test from a broken build, so each failed run costs
one more call for its jobs. That step goes in the title because it is what
repeats across failures, and repetition is what clusters them; the commit that
triggered the run goes in the body.

The cursor is the latest created_at seen, passed back as the API's `created`
filter. Ids carry the attempt number: a re-run that fails again is a new event.
"""
import os
from collections.abc import Iterator

import httpx

from aiops.envelope import Event
from aiops.registry import Source, register


@register("github_actions")
class GitHubActionsSource(Source):
    def __init__(self, repo: str, branch: str | None = None,
                 token: str | None = None, client: httpx.Client | None = None,
                 per_page: int = 100):
        self.repo = repo
        self.branch = branch
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.client = client or httpx.Client(base_url="https://api.github.com",
                                             timeout=30)
        self.per_page = per_page
        self.cursor: str | None = None

    def _failed_step(self, run_id: int, headers: dict) -> str | None:
        r = self.client.get(f"/repos/{self.repo}/actions/runs/{run_id}/jobs",
                            params={"filter": "latest"}, headers=headers)
        r.raise_for_status()
        for job in r.json()["jobs"]:
            if job.get("conclusion") != "failure":
                continue
            for step in job.get("steps") or []:
                if step.get("conclusion") == "failure":
                    return f"{job['name']} / {step['name']}"
            return job["name"]
        return None

    def fetch(self, cursor: str | None = None) -> Iterator[Event]:
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        params = {"status": "failure", "per_page": str(self.per_page)}
        if self.branch:
            params["branch"] = self.branch
        if cursor:
            params["created"] = f">{cursor}"
        r = self.client.get(f"/repos/{self.repo}/actions/runs",
                            params=params, headers=headers)
        r.raise_for_status()
        for run in r.json()["workflow_runs"]:
            created = run["created_at"]
            if self.cursor is None or created > self.cursor:
                self.cursor = created
            title = f"{run['name']} failed on {run['head_branch']}"
            step = self._failed_step(run["id"], headers)
            if step:
                title += f": {step}"
            yield Event(
                id=f"github:{self.repo}:run:{run['id']}:{run['run_attempt']}",
                source=f"github://{self.repo}/actions",
                type="com.github.workflow_run",
                subject=str(run["id"]),
                time=run["updated_at"],
                title=title,
                body=f"Triggered by {run['event']}: {run['display_title']}",
                url=run["html_url"],
                severitytext="error",
                severitynumber=17,
                attributes={"workflow": run["name"],
                            "branch": run["head_branch"] or "",
                            "event": run["event"],
                            "sha": run.get("head_sha", "")},
            )
