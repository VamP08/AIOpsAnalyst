import textwrap

import httpx

from aiops.pipeline import Pipeline
from aiops.registry import Source, register

NGINX = ('203.0.113.9 - - [02/Sep/2026:10:15:32 +0000] "GET /a HTTP/1.1" '
         '500 1 "-" "x"\n')


@register("boom")
class BoomSource(Source):
    def fetch(self, cursor=None):
        raise httpx.RemoteProtocolError(
            "Server disconnected without sending a response.")


def test_failing_source_reports_error_and_others_still_ingest(tmp_path):
    log = tmp_path / "access.log"
    log.write_text(NGINX, encoding="utf-8")
    config = tmp_path / "pipeline.yaml"
    config.write_text(textwrap.dedent(f"""
        store: {(tmp_path / "db.sqlite").as_posix()}
        sources:
          - id: unstable-api
            adapter: boom
          - id: nginx
            adapter: log_file
            config:
              path: {log.as_posix()}
              format: nginx_access
              source: syslog://web-1/nginx
    """), encoding="utf-8")

    pipe = Pipeline.from_yaml(str(config))
    result = pipe.ingest()
    assert result["nginx"] == 1
    assert "RemoteProtocolError" in result["unstable-api"]
    assert pipe.store.count_events() == 1
    # failed source keeps no cursor: full retry next run
    assert pipe.store.get_cursor("unstable-api") is None
