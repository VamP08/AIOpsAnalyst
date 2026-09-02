"""LLM router over stacked free tiers.

Every provider speaks the OpenAI chat-completions shape, so one request body
works for all. Order is the failover order: first provider that has a key and
answers wins. Returns None when they all fail — the pipeline then leaves the
cluster untriaged rather than guessing. Which model actually answered is
recorded on every reply; the eval reports the mix.

Model names drift as free tiers churn; each is overridable by env var
(AIOPS_MODEL_<NAME>) without a code change.
"""
import os
import sys
from typing import NamedTuple

import httpx

GROQ = "https://api.groq.com/openai/v1"

# Groq appears three times: it meters tokens per minute per model, so each
# model is a separate budget. Strongest first — falling back costs quality
# only under load.
PROVIDERS = [
    ("groq", "GROQ_API_KEY", GROQ, "openai/gpt-oss-120b"),
    ("groq_qwen", "GROQ_API_KEY", GROQ, "qwen/qwen3.8-27b"),
    ("groq_20b", "GROQ_API_KEY", GROQ, "openai/gpt-oss-20b"),
    ("cerebras", "CEREBRAS_API_KEY", "https://api.cerebras.ai/v1",
     "llama-3.3-70b"),
    ("gemini", "GEMINI_API_KEY",
     "https://generativelanguage.googleapis.com/v1beta/openai",
     "gemini-2.0-flash"),
    ("openrouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1",
     "meta-llama/llama-3.3-70b-instruct:free"),
]

_client = httpx.Client(timeout=60)


class Reply(NamedTuple):
    text: str
    model: str


def _model(name: str, default: str) -> str:
    return os.environ.get(f"AIOPS_MODEL_{name.upper()}", default)


def _call(base: str, key: str, model: str, messages: list[dict],
          max_tokens: int) -> str | None:
    r = _client.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "messages": messages,
              "max_tokens": max_tokens, "temperature": 0.0,
              "response_format": {"type": "json_object"}},
    )
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    return content.strip() or None


def chat(messages: list[dict], max_tokens: int = 2000) -> Reply | None:
    """max_tokens covers reasoning too: gpt-oss spends most of the budget
    thinking, and a tight cap truncates the JSON mid-object."""
    for name, env_key, base, default_model in PROVIDERS:
        key = os.environ.get(env_key)
        if not key:
            continue
        model = _model(name, default_model)
        try:
            answer = _call(base, key, model, messages, max_tokens)
            if answer:
                return Reply(answer, model)
            print(f"llm: {name} returned empty content", file=sys.stderr)
        except httpx.HTTPStatusError as e:
            print(f"llm: {name} {e.response.status_code} "
                  f"{e.response.text[:200]}", file=sys.stderr)
        except (httpx.HTTPError, KeyError, IndexError) as e:
            print(f"llm: {name} {type(e).__name__}: {e}", file=sys.stderr)
    return None
