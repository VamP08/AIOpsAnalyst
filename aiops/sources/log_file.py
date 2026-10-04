"""File-based log source: nginx, Apache, syslog, JSON-lines, BGL, OpenStack, ZooKeeper.

Event ids hash (source, line number, raw line): re-ingesting the same file
yields the same ids — the store's primary key makes ingestion idempotent —
while identical lines at different positions stay distinct events. The cursor
is the count of consumed lines, so a later fetch picks up appended lines only.
"""
import hashlib
import json
import re
from collections.abc import Iterator
from datetime import datetime

from aiops.envelope import Event, severity_number
from aiops.registry import Source, register

ACCESS_RE = re.compile(
    r'(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] '
    r'"(?P<method>\S+) (?P<path>\S+)[^"]*" (?P<status>\d{3}) \S+'
)
ERROR_RE = re.compile(
    r'(?P<time>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}) \[(?P<level>\w+)\] '
    r'\d+#\d+: (?:\*\d+ )?(?P<msg>.*)'
)
APACHE_RE = re.compile(
    r'\[(?P<time>[^\]]+)\] \[(?P<level>\w+)\] '
    r'(?:\[client (?P<client>[^\]]+)\] )?(?P<msg>.*)'
)
# BGL ships with an operator-applied alert label as the first field. It is
# ground truth for the evaluation, so it is captured into attributes and kept
# out of every field the model reads - the prompt builds from title and body.
BGL_RE = re.compile(
    r'(?P<label>\S+) (?P<epoch>\d+) (?P<date>\S+) (?P<node>\S+) '
    r'(?P<stamp>\S+) (?P<node2>\S+) (?P<kind>\S+) (?P<component>\S+) '
    r'(?P<level>\S+) (?P<msg>.*)'
)
SYSLOG_RE = re.compile(
    r'\w{3}\s+\d+ \d{2}:\d{2}:\d{2} (?P<host>\S+) '
    r'(?P<proc>[\w./()-]+)(?:\[\d+\])?: ?(?P<msg>.*)'
)
# Loghub's OpenStack lines lead with the file they came from; the request
# context in brackets varies per line and says nothing about what happened.
OPENSTACK_RE = re.compile(
    r'(?P<service>[\w-]+)\.log\S* (?P<time>\S+ \S+) \d+ (?P<level>\w+) '
    r'(?P<component>\S+) (?:\[[^\]]*\] )?(?P<msg>.*)'
)
ZOOKEEPER_RE = re.compile(
    r'(?P<time>\S+ \S+) - (?P<level>\w+)\s+\[.*?(?P<component>[\w$.]+)@\d+\] '
    r'- (?P<msg>.*)'
)


def _parse_nginx_access(raw: str) -> dict:
    m = ACCESS_RE.match(raw)
    if not m:
        return {}
    status = int(m["status"])
    severity = 17 if status >= 500 else 13 if status >= 400 else 9
    time = datetime.strptime(m["time"], "%d/%b/%Y:%H:%M:%S %z").isoformat()
    return {"title": f'{m["method"]} {m["path"]} {status}', "time": time,
            "severitynumber": severity,
            "attributes": {"ip": m["ip"], "status": str(status)}}


def _parse_nginx_error(raw: str) -> dict:
    m = ERROR_RE.match(raw)
    if not m:
        return {}
    return {"title": m["msg"], "severitytext": m["level"],
            "severitynumber": severity_number(m["level"])}


def _parse_apache_error(raw: str) -> dict:
    m = APACHE_RE.match(raw)
    if not m:
        return {}
    fields = {"title": m["msg"], "severitytext": m["level"],
              "severitynumber": severity_number(m["level"]),
              "time": datetime.strptime(m["time"],
                                        "%a %b %d %H:%M:%S %Y").isoformat()}
    if m["client"]:
        fields["attributes"] = {"client": m["client"]}
    return fields


def _parse_syslog(raw: str) -> dict:
    m = SYSLOG_RE.match(raw)
    if not m:
        return {}
    return {"title": m["msg"],
            "attributes": {"host": m["host"], "proc": m["proc"]}}


def _parse_jsonl(raw: str) -> dict:
    try:
        record = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(record, dict):
        return {}
    time = next((record.pop(k) for k in ("time", "timestamp", "ts")
                 if k in record), None)
    level = next((record.pop(k) for k in ("level", "severity")
                  if k in record), None)
    title = next((record.pop(k) for k in ("message", "msg")
                  if k in record), None)
    out = {"attributes": {k: str(v) for k, v in record.items()}}
    if time is not None:
        out["time"] = str(time)
    if level is not None:
        out["severitytext"] = str(level)
        out["severitynumber"] = severity_number(str(level))
    if title is not None:
        out["title"] = str(title)
    return out


def _parse_bgl(raw: str) -> dict:
    m = BGL_RE.match(raw)
    if not m:
        return {}
    try:
        stamp = datetime.strptime(m["stamp"], "%Y-%m-%d-%H.%M.%S.%f").isoformat()
    except ValueError:
        stamp = None
    fields = {
        "title": m["msg"],
        "severitytext": m["level"],
        "severitynumber": severity_number(m["level"]),
        "attributes": {"node": m["node"], "component": m["component"],
                       "kind": m["kind"], "bgl_label": m["label"]},
    }
    if stamp:
        fields["time"] = stamp
    return fields


def _parse_openstack(raw: str) -> dict:
    m = OPENSTACK_RE.match(raw)
    if not m:
        return {}
    return {"title": m["msg"], "severitytext": m["level"],
            "severitynumber": severity_number(m["level"]),
            "time": datetime.fromisoformat(m["time"]).isoformat(),
            "attributes": {"service": m["service"],
                           "component": m["component"]}}


def _parse_zookeeper(raw: str) -> dict:
    m = ZOOKEEPER_RE.match(raw)
    if not m:
        return {}
    return {"title": m["msg"], "severitytext": m["level"],
            "severitynumber": severity_number(m["level"]),
            "time": datetime.strptime(m["time"],
                                      "%Y-%m-%d %H:%M:%S,%f").isoformat(),
            "attributes": {"component": m["component"]}}


_PARSERS = {
    "nginx_access": _parse_nginx_access,
    "nginx_error": _parse_nginx_error,
    "apache_error": _parse_apache_error,
    "syslog": _parse_syslog,
    "jsonl": _parse_jsonl,
    "bgl": _parse_bgl,
    "openstack": _parse_openstack,
    "zookeeper": _parse_zookeeper,
}


@register("log_file")
class LogFileSource(Source):
    def __init__(self, path: str, format: str, source: str):
        self.path = path
        self.parse = _PARSERS[format]
        self.source = source
        self.cursor = "0"

    def fetch(self, cursor: str | None = None) -> Iterator[Event]:
        consumed = start = int(cursor or 0)
        with open(self.path, encoding="utf-8", errors="replace") as f:
            for lineno, line in enumerate(f):
                consumed = lineno + 1
                self.cursor = str(consumed)
                if lineno < start:
                    continue
                raw = line.rstrip("\r\n")
                if not raw.strip():
                    continue
                fields = self.parse(raw)
                fields.setdefault("title", raw)
                fields.setdefault("severitynumber", 0)
                digest = hashlib.sha256(
                    f"{self.source}\n{lineno}\n{raw}".encode()).hexdigest()[:24]
                yield Event(id=digest, source=self.source,
                            type="dev.aiops.log.line", raw=raw, **fields)
