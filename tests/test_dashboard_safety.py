"""The dashboard renders text written by strangers.

Issue titles and bodies come from whoever opened the issue, and the summary
comes from a model reading that same text, so a title carrying markup must
never become markup. The rendering builds nodes and fills them with
textContent; these tests fail if someone reaches for an HTML string again.
"""
from pathlib import Path

APP = (Path(__file__).resolve().parent.parent / "web" / "app.js").read_text(
    encoding="utf-8")


def test_no_html_string_assignment_in_the_dashboard():
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
        assert sink not in APP, f"{sink} reintroduces the injection surface"


def test_urls_are_scheme_checked_before_reaching_an_href():
    assert "function safeUrl" in APP
    assert "/^https?:$/.test(url.protocol)" in APP


def test_tier_and_ticket_values_are_validated_before_use():
    assert 'TIERS = new Set(["auto", "suggest", "escalate", "abstain"])' in APP
    assert "TICKET = /^[A-Z][A-Z0-9]*-\d+$/" in APP
