from aiops.sources.log_file import LogFileSource

NGINX_ACCESS = (
    '203.0.113.9 - - [02/Sep/2026:10:15:32 +0000] "GET /api/checkout HTTP/1.1" '
    '502 157 "-" "Mozilla/5.0"\n'
    '203.0.113.9 - - [02/Sep/2026:10:15:33 +0000] "GET /health HTTP/1.1" '
    '200 2 "-" "kube-probe/1.29"\n'
)

NGINX_ERROR = (
    "2026/09/02 10:15:32 [error] 4123#0: *88 upstream timed out "
    "(110: Connection timed out) while reading response header from upstream\n"
)

SYSLOG = "Sep  2 10:15:32 web-1 sshd[2201]: Failed password for root from 198.51.100.7 port 22\n"

JSONL = (
    '{"time": "2026-09-02T10:15:32Z", "level": "error", '
    '"message": "payment declined", "service": "checkout"}\n'
)


def write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


def test_nginx_access_lines_become_events(tmp_path):
    src = LogFileSource(path=write(tmp_path, "access.log", NGINX_ACCESS),
                        format="nginx_access", source="syslog://web-1/nginx")
    events = list(src.fetch())
    assert len(events) == 2
    e = events[0]
    assert e.source == "syslog://web-1/nginx"
    assert e.type == "dev.aiops.log.line"
    assert e.title == "GET /api/checkout 502"
    assert e.severitynumber == 17  # 5xx -> ERROR
    assert e.time == "2026-09-02T10:15:32+00:00"
    assert e.raw.startswith("203.0.113.9")
    assert events[1].severitynumber == 9  # 200 -> INFO


def test_nginx_error_line_parses_level_and_message(tmp_path):
    src = LogFileSource(path=write(tmp_path, "error.log", NGINX_ERROR),
                        format="nginx_error", source="syslog://web-1/nginx-err")
    [e] = list(src.fetch())
    assert e.severitytext == "error"
    assert e.severitynumber == 17
    assert "upstream timed out" in e.title


def test_syslog_line_parses_host_and_process(tmp_path):
    src = LogFileSource(path=write(tmp_path, "auth.log", SYSLOG),
                        format="syslog", source="syslog://web-1/auth")
    [e] = list(src.fetch())
    assert e.attributes["host"] == "web-1"
    assert e.attributes["proc"] == "sshd"
    assert e.title.startswith("Failed password")


def test_jsonl_line_maps_common_keys_and_keeps_rest_as_attributes(tmp_path):
    src = LogFileSource(path=write(tmp_path, "app.log", JSONL),
                        format="jsonl", source="app://checkout")
    [e] = list(src.fetch())
    assert e.title == "payment declined"
    assert e.severitytext == "error"
    assert e.time == "2026-09-02T10:15:32Z"
    assert e.attributes["service"] == "checkout"


def test_event_ids_are_deterministic_across_reingest(tmp_path):
    path = write(tmp_path, "access.log", NGINX_ACCESS)
    ids_a = [e.id for e in LogFileSource(path=path, format="nginx_access",
                                         source="s").fetch()]
    ids_b = [e.id for e in LogFileSource(path=path, format="nginx_access",
                                         source="s").fetch()]
    assert ids_a == ids_b
    assert len(set(ids_a)) == 2  # duplicate-free within one file


def test_identical_lines_at_different_positions_get_distinct_ids(tmp_path):
    line = '{"level": "info", "message": "tick"}\n'
    path = write(tmp_path, "app.log", line + line)
    ids = [e.id for e in LogFileSource(path=path, format="jsonl", source="s").fetch()]
    assert len(ids) == 2
    assert ids[0] != ids[1]


def test_cursor_resumes_after_consumed_lines(tmp_path):
    path = write(tmp_path, "access.log", NGINX_ACCESS)
    src = LogFileSource(path=path, format="nginx_access", source="s")
    first = list(src.fetch())
    assert len(first) == 2
    resumed = list(LogFileSource(path=path, format="nginx_access",
                                 source="s").fetch(cursor=src.cursor))
    assert resumed == []

    with open(path, "a", encoding="utf-8") as f:
        f.write('203.0.113.9 - - [02/Sep/2026:10:16:00 +0000] "GET / HTTP/1.1" '
                '404 12 "-" "curl/8.0"\n')
    tail = list(LogFileSource(path=path, format="nginx_access",
                              source="s").fetch(cursor=src.cursor))
    assert len(tail) == 1
    assert tail[0].title == "GET / 404"
    assert tail[0].severitynumber == 13  # 4xx -> WARN


def test_unparseable_line_still_becomes_an_event_with_raw_preserved(tmp_path):
    path = write(tmp_path, "weird.log", "not a log line at all\n")
    [e] = list(LogFileSource(path=path, format="nginx_access", source="s").fetch())
    assert e.raw == "not a log line at all"
    assert e.title == "not a log line at all"
    assert e.severitynumber == 0
