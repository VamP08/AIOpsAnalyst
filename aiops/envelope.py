"""One event shape for every source.

CloudEvents attribute model: required id/source/type/specversion, optional
time/subject/datacontenttype, extensions inline at the top level per the CE JSON
format. Extension names must be lowercase a-z0-9, max 20 chars — hence
severitynumber, not severity_number. Payload fields live under data.

Severity uses OpenTelemetry's 1-24 scale (TRACE 1, DEBUG 5, INFO 9, WARN 13,
ERROR 17, FATAL 21) so syslog levels, nginx statuses and app-log strings sort on
one axis; 0 means the source gave no usable level.
"""
from dataclasses import dataclass, field

_LEVELS = {
    "trace": 1,
    "debug": 5,
    "info": 9, "notice": 9,
    "warn": 13, "warning": 13,
    "error": 17, "err": 17,
    "fatal": 21, "critical": 21, "crit": 21, "emerg": 21, "alert": 21, "panic": 21,
}

_EXTENSIONS = ("time", "subject", "datacontenttype", "severitytext",
               "severitynumber", "fingerprint", "clusterid")


def severity_number(text: str) -> int:
    return _LEVELS.get(text.strip().lower(), 0)


@dataclass(frozen=True)
class Event:
    id: str
    source: str
    type: str
    specversion: str = "1.0"
    time: str | None = None
    subject: str | None = None
    datacontenttype: str | None = None
    severitytext: str | None = None
    severitynumber: int | None = None
    fingerprint: str | None = None
    clusterid: str | None = None
    title: str = ""
    body: str | None = None
    attributes: dict = field(default_factory=dict)
    url: str | None = None
    raw: str | None = None

    def to_dict(self) -> dict:
        d = {"specversion": self.specversion, "id": self.id,
             "source": self.source, "type": self.type}
        for key in _EXTENSIONS:
            value = getattr(self, key)
            if value is not None:
                d[key] = value
        data = {"title": self.title}
        for key in ("body", "url", "raw"):
            value = getattr(self, key)
            if value is not None:
                data[key] = value
        if self.attributes:
            data["attributes"] = self.attributes
        d["data"] = data
        return d
