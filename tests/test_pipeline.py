import textwrap

from aiops.pipeline import Pipeline

NGINX = (
    '203.0.113.9 - - [02/Sep/2026:10:15:32 +0000] "GET /a HTTP/1.1" 500 1 "-" "x"\n'
    '203.0.113.9 - - [02/Sep/2026:10:15:33 +0000] "GET /b HTTP/1.1" 200 1 "-" "x"\n'
)


def write_config(tmp_path, log_path):
    config = tmp_path / "pipeline.yaml"
    config.write_text(textwrap.dedent(f"""
        store: {(tmp_path / "db.sqlite").as_posix()}
        sources:
          - id: nginx-web-1
            adapter: log_file
            config:
              path: {log_path.as_posix()}
              format: nginx_access
              source: syslog://web-1/nginx
    """), encoding="utf-8")
    return str(config)


def test_ingest_pulls_all_sources_into_store(tmp_path):
    log = tmp_path / "access.log"
    log.write_text(NGINX, encoding="utf-8")
    pipe = Pipeline.from_yaml(write_config(tmp_path, log))
    assert pipe.ingest() == {"nginx-web-1": 2}
    assert pipe.store.count_events() == 2


def test_second_ingest_resumes_from_cursor(tmp_path):
    log = tmp_path / "access.log"
    log.write_text(NGINX, encoding="utf-8")
    config = write_config(tmp_path, log)
    Pipeline.from_yaml(config).ingest()

    # a fresh Pipeline instance simulates a new cron run
    pipe = Pipeline.from_yaml(config)
    assert pipe.ingest() == {"nginx-web-1": 0}

    with open(log, "a", encoding="utf-8") as f:
        f.write('203.0.113.9 - - [02/Sep/2026:10:16:00 +0000] '
                '"GET /c HTTP/1.1" 200 1 "-" "x"\n')
    assert Pipeline.from_yaml(config).ingest() == {"nginx-web-1": 1}
    assert Pipeline.from_yaml(config).store.count_events() == 3
