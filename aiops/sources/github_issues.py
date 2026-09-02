"""GitHub issues of any public repo as an event stream.

Cursor is the max updated_at seen, passed back as the API's `since` filter, so
a stateless cron run picks up only what changed. The event id includes
updated_at: re-reading the same state is idempotent, while an edit produces a
new event — an issue that changed deserves a fresh look. Pull requests come
through the issues API too and are skipped.
"""
import os
from collections.abc import Iterator

import httpx

from aiops.envelope import Event
from aiops.registry import Source, register


@register("github_issues")
class GitHubIssuesSource(Source):
    def __init__(self, repo: str, token: str | None = None,
                 client: httpx.Client | None = None, max_pages: int = 10):
        self.repo = repo
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.client = client or httpx.Client(base_url="https://api.github.com",
                                             timeout=30)
        self.max_pages = max_pages
        self.cursor: str | None = None

    def fetch(self, cursor: str | None = None) -> Iterator[Event]:
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        params = {"state": "all", "per_page": "100",
                  "sort": "updated", "direction": "asc"}
        if cursor:
            params["since"] = cursor
        url: str | None = f"/repos/{self.repo}/issues"
        for _ in range(self.max_pages):  # bounded batch; cursor resumes the rest
            if not url:
                break
            r = self.client.get(url, params=params, headers=headers)
            r.raise_for_status()
            for issue in r.json():
                if "pull_request" in issue:
                    continue
                updated = issue["updated_at"]
                if self.cursor is None or updated > self.cursor:
                    self.cursor = updated
                yield Event(
                    id=f"github:{self.repo}:{issue['number']}:{updated}",
                    source=f"github://{self.repo}",
                    type="com.github.issue",
                    subject=str(issue["number"]),
                    time=updated,
                    title=issue["title"] or "",
                    body=issue.get("body") or None,
                    url=issue["html_url"],
                    attributes={
                        "labels": ",".join(
                            label["name"] for label in issue.get("labels", [])),
                        "state": issue["state"],
                        "author": (issue.get("user") or {}).get("login", ""),
                    },
                )
            url = r.links.get("next", {}).get("url")
            # None, not {}: httpx replaces the URL's query with `params` when
            # one is given, and the Link URL already carries the full query —
            # stripping it turns paging into an infinite default listing.
            params = None
