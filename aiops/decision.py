"""What a sink receives: a triaged cluster, with its evidence attached.

Sinks never see a raw verdict or touch the store — everything they need to
write a ticket or a message is here, including the sample events so the ticket
can cite what it was based on.
"""
from dataclasses import dataclass, field

from aiops.envelope import Event


@dataclass(frozen=True)
class Decision:
    cluster_id: str
    label: str
    tier: str
    category: str
    severity: str
    summary: str
    confidence: float
    size: int
    evidence: list[Event] = field(default_factory=list)

    def evidence_lines(self) -> list[str]:
        """Distinct samples only: three identical lines from one log template
        fill a ticket without telling the reader anything."""
        lines, seen = [], set()
        for event in self.evidence:
            line = f"- {event.title}" + (f" ({event.url})" if event.url else "")
            if line not in seen:
                seen.add(line)
                lines.append(line)
        return lines
