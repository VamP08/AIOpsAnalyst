"""Incidents from any Atlassian Statuspage (Cloudflare, GitHub, Datadog...).

Every Statuspage serves the same unauthenticated JSON at
/api/v2/incidents.json: the 50 most recent incidents, no paging and no `since`
filter, so the cursor (max updated_at seen) is applied here. The body is the
first update posted - what was known when the incident was raised, which is
what a triager would have had in front of them, not the resolution note.
"""
from collections.abc import Iterator

import httpx

from aiops.envelope import Event
from aiops.registry import Source, register

# Statuspage's own impact scale, onto OpenTelemetry severity.
_IMPACT = {"none": 9, "minor": 13, "major": 17, "critical": 21}


@register("statuspage")
class StatuspageSource(Source):
    def __init__(self, page: str, client: httpx.Client | None = None):
        self.page = page
        self.client = client or httpx.Client(timeout=30)
        self.cursor: str | None = None

    def fetch(self, cursor: str | None = None) -> Iterator[Event]:
        r = self.client.get(f"https://{self.page}/api/v2/incidents.json")
        r.raise_for_status()
        for incident in r.json()["incidents"]:
            updated = incident["updated_at"]
            if cursor and updated <= cursor:
                continue
            if self.cursor is None or updated > self.cursor:
                self.cursor = updated
            updates = incident.get("incident_updates") or []
            impact = incident.get("impact") or "none"
            yield Event(
                id=f"statuspage:{self.page}:{incident['id']}:{updated}",
                source=f"statuspage://{self.page}",
                type="com.statuspage.incident",
                subject=incident["id"],
                time=updated,
                title=incident["name"],
                body=updates[-1]["body"] if updates else None,
                url=f"https://{self.page}/incidents/{incident['id']}",
                severitytext=impact,
                severitynumber=_IMPACT.get(impact, 0),
                attributes={
                    "impact": impact,
                    "status": incident.get("status", ""),
                    "components": ",".join(
                        c["name"] for c in incident.get("components") or []),
                },
            )
