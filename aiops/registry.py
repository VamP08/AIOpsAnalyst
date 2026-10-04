"""Adapter contract and registry.

A source turns some feed into Events; a sink turns a triage decision into an
action. The pipeline core only ever looks adapters up by name here, so adding a
source means adding one module — nothing in the core changes. Registration is a
decorator into a module dict; entry points would replace this if adapters ever
ship as separate packages.
"""
from abc import ABC, abstractmethod
from collections.abc import Iterator

from aiops.envelope import Event

SOURCES: dict[str, type["Source"]] = {}
SINKS: dict[str, type["Sink"]] = {}


class Source(ABC):
    @abstractmethod
    def fetch(self, cursor: str | None = None) -> Iterator[Event]: ...

    def check(self) -> bool:
        """Credentials/reachability smoke test; override where it means something."""
        return True


class Sink(ABC):
    @abstractmethod
    def emit(self, decision) -> str | None:
        """Returns a reference to what was created (a ticket key) when the
        sink has one, so the store can record it."""

    def check(self) -> bool:
        """Credentials/config smoke test; override where it means something."""
        return True


def register(name: str):
    def wrap(cls):
        registry = SOURCES if issubclass(cls, Source) else SINKS
        if name in registry:
            raise ValueError(f"adapter name already registered: {name!r}")
        registry[name] = cls
        return cls
    return wrap


def create(name: str, config: dict):
    registry = SOURCES if name in SOURCES else SINKS
    if name not in registry:
        known = sorted([*SOURCES, *SINKS])
        raise KeyError(f"unknown adapter {name!r}; registered: {known}")
    return registry[name](**config)
