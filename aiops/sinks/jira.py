"""Jira Cloud issue creation over REST v2.

v2 rather than v3 on purpose: v3 requires the description in Atlassian
Document Format, and a plain string is all this needs. Works on the free plan —
API access follows project permissions, not billing tier.
"""
import os

import httpx

from aiops.decision import Decision
from aiops.registry import Sink, register


# A tracker distinguishes a defect from a request; the taxonomy already knows
# which is which, so the ticket arrives as the right type instead of a pile of
# identical tasks. Anything unmapped falls back to Task.
ISSUE_TYPES = {"crash": "Bug", "error": "Bug", "feature_request": "Story"}


@register("jira")
class JiraSink(Sink):
    def __init__(self, base_url: str | None = None, project: str | None = None,
                 email: str | None = None, token: str | None = None,
                 issue_type: str | None = None,
                 client: httpx.Client | None = None):
        self.base_url = (base_url or os.environ.get("JIRA_BASE_URL", "")
                         ).rstrip("/")
        self.project = project or os.environ.get("JIRA_PROJECT", "")
        self.email = email or os.environ.get("JIRA_EMAIL", "")
        self.token = token or os.environ.get("JIRA_API_TOKEN", "")
        self.issue_type = issue_type
        self.client = client or httpx.Client(timeout=30)

    def _issue_type(self, category: str) -> str:
        return self.issue_type or ISSUE_TYPES.get(category, "Task")

    def check(self) -> bool:
        return all([self.base_url, self.project, self.email, self.token])

    def _description(self, decision: Decision) -> str:
        return "\n".join([
            decision.summary,
            "",
            f"Cluster: {decision.cluster_id}",
            f"Pattern: {decision.label}",
            f"Events: {decision.size}",
            f"Triage: {decision.category} / {decision.severity} / "
            f"confidence {decision.confidence:.2f} / tier {decision.tier}",
            "",
            "Evidence:",
            *decision.evidence_lines(),
        ])

    def emit(self, decision: Decision) -> str | None:
        r = self.client.post(
            f"{self.base_url}/rest/api/2/issue",
            auth=(self.email, self.token),
            json={"fields": {
                "project": {"key": self.project},
                "issuetype": {"name": self._issue_type(decision.category)},
                "summary": f"[{decision.category}] {decision.summary}"[:250],
                "description": self._description(decision),
            }},
        )
        r.raise_for_status()
        return r.json()["key"]
