"""The explore page renders text written by strangers.

Issue titles and bodies come from whoever opened the issue, and the summary
comes from a model reading that same text, so a title carrying markup must
never become markup. The page builds nodes and fills them with textContent;
these tests fail if someone reaches for an HTML string again.
"""
from pathlib import Path

APP = (Path(__file__).resolve().parent.parent / "web" / "src" / "scripts"
       / "explore.ts").read_text(encoding="utf-8")


def test_no_html_string_assignment_in_the_explore_page():
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
        assert sink not in APP, f"{sink} reintroduces the injection surface"


def test_links_are_only_built_from_https_urls():
    assert 'sm.url?.startsWith("https://")' in APP
    assert "a.href = sm.url" in APP
