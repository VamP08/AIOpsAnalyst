import os

from aiops.envfile import load_env


def test_load_env_sets_missing_vars_only(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "FOO_KEY=abc123\n"
        "# comment line\n"
        "\n"
        "BAR_KEY=with=equals\n"
        "EMPTY_KEY=\n",
        encoding="utf-8")
    monkeypatch.delenv("FOO_KEY", raising=False)
    monkeypatch.setenv("BAR_KEY", "already-set")
    load_env(str(env))
    assert os.environ["FOO_KEY"] == "abc123"
    assert os.environ["BAR_KEY"] == "already-set"  # real env wins
    assert "EMPTY_KEY" not in os.environ


def test_load_env_missing_file_is_a_noop(tmp_path):
    load_env(str(tmp_path / "absent.env"))
