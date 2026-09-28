import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

from live_feed import merge


def entry(eid, when, summary="s"):
    return {"id": eid, "seen": when, "summary": summary}


def test_merge_puts_newest_first_and_caps_the_feed():
    existing = [entry("b", "2026-09-27T10:00"), entry("a", "2026-09-26T10:00")]
    fresh = [entry("c", "2026-09-28T10:00")]
    merged = merge(existing, fresh, cap=2)
    assert [e["id"] for e in merged] == ["c", "b"]


def test_merge_replaces_an_entry_seen_again_rather_than_duplicating():
    existing = [entry("a", "2026-09-26T10:00", "old summary")]
    fresh = [entry("a", "2026-09-28T10:00", "new summary")]
    merged = merge(existing, fresh, cap=10)
    assert len(merged) == 1
    assert merged[0]["summary"] == "new summary"


def test_merge_of_nothing_keeps_what_was_there():
    existing = [entry("a", "2026-09-26T10:00")]
    assert merge(existing, [], cap=10) == existing


def test_fallback_encoder_separates_texts_without_sentence_transformers():
    from live_feed import lexical_encoder

    [a, b, same] = lexical_encoder(["disk full on /dev/sda1",
                                    "please add dark mode",
                                    "disk full on /dev/sda1"])
    dot = lambda x, y: sum(p * q for p, q in zip(x, y))
    assert dot(a, same) > 0.999          # identical text stays identical
    assert abs(dot(a, b)) < 0.5          # different text does not collapse together
    assert abs(dot(a, a) - 1) < 1e-9     # unit vectors, so cosine is the dot
