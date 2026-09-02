"""Verdict contract between the LLM and everything downstream.

Small on purpose: enums for category and severity, bounded confidence,
evidence as event ids. Anything that fails validation is treated as no verdict
at all — a cluster stays untriaged rather than carrying a malformed label.
"""
import json
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

CATEGORIES = ("crash", "error", "performance", "feature_request",
              "question", "noise")
SEVERITIES = ("low", "medium", "high", "critical")

_JSON = re.compile(r"\{.*\}", re.DOTALL)


class Verdict(BaseModel):
    category: Literal[*CATEGORIES]
    severity: Literal[*SEVERITIES]
    summary: str = Field(max_length=300)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = []


def parse_verdict(text: str) -> Verdict | None:
    match = _JSON.search(text or "")
    if not match:
        return None
    try:
        return Verdict.model_validate(json.loads(match.group()))
    except (ValueError, ValidationError):
        return None
