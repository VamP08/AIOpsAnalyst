import httpx
import pytest

import aiops.triage.llm as llm


def reply(content):
    return {"choices": [{"message": {"content": content}}]}


def install(monkeypatch, handler, env=None):
    for name in ("GROQ_API_KEY", "CEREBRAS_API_KEY", "GEMINI_API_KEY",
                 "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(
        llm, "_client", httpx.Client(transport=httpx.MockTransport(handler)))


def test_first_provider_with_key_answers(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=reply('{"ok": true}'))

    install(monkeypatch, handler, {"GROQ_API_KEY": "k"})
    result = llm.chat([{"role": "user", "content": "hi"}])
    assert result.text == '{"ok": true}'
    assert result.model  # which model actually answered is recorded
    assert calls[0].headers["Authorization"] == "Bearer k"
    assert "groq.com" in str(calls[0].url)


def test_failover_skips_erroring_provider(monkeypatch):
    def handler(request):
        if "groq.com" in str(request.url):
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(200, json=reply("from-fallback"))

    install(monkeypatch, handler,
            {"GROQ_API_KEY": "k1", "OPENROUTER_API_KEY": "k2"})
    result = llm.chat([{"role": "user", "content": "hi"}])
    assert result.text == "from-fallback"


def test_providers_without_keys_are_not_called(monkeypatch):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json=reply("x"))

    install(monkeypatch, handler, {"OPENROUTER_API_KEY": "k"})
    llm.chat([{"role": "user", "content": "hi"}])
    assert all("openrouter" in u for u in calls)


def test_all_fail_returns_none(monkeypatch):
    install(monkeypatch, lambda r: httpx.Response(500), {"GROQ_API_KEY": "k"})
    assert llm.chat([{"role": "user", "content": "hi"}]) is None


def test_empty_content_falls_through(monkeypatch):
    def handler(request):
        if "groq.com" in str(request.url):
            return httpx.Response(200, json=reply(""))
        return httpx.Response(200, json=reply("real"))

    install(monkeypatch, handler,
            {"GROQ_API_KEY": "k1", "OPENROUTER_API_KEY": "k2"})
    assert llm.chat([{"role": "user", "content": "hi"}]).text == "real"


def test_model_overridable_by_env(monkeypatch):
    seen = {}

    def handler(request):
        seen["body"] = request.read()
        return httpx.Response(200, json=reply("x"))

    install(monkeypatch, handler, {"GROQ_API_KEY": "k",
                                   "AIOPS_MODEL_GROQ": "my-custom-model"})
    llm.chat([{"role": "user", "content": "hi"}])
    assert b"my-custom-model" in seen["body"]
