"""Tier-1 clustering: deterministic fingerprint over configured key fields.

The Alertmanager/PagerDuty pattern for structured events: hash the fields that
identify an incident, exclude the ones that vary per occurrence (instance,
timestamp). Which fields go in the key is per-source config — too coarse merges
unrelated incidents, too fine floods, and only the source knows its own labels.
"""
import hashlib

from aiops.envelope import Event


def _lookup(event: Event, path: str) -> str:
    if path.startswith("attributes."):
        return str(event.attributes.get(path.removeprefix("attributes."), ""))
    return str(getattr(event, path, "") or "")


def compute_fingerprint(event: Event, fields: tuple[str, ...]) -> str:
    material = "\x1f".join(_lookup(event, f) for f in fields)
    return hashlib.sha256(material.encode()).hexdigest()[:16]
