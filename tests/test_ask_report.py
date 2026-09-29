import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

from ask_report import hit_rank, score


def match(label, summary=""):
    return {"label": label, "summary": summary}


def test_hit_rank_is_the_position_of_the_first_matching_cluster():
    matches = [match("Disk full on <*>"), match("Failed password for <*>")]
    assert hit_rank(matches, "Failed password") == 2


def test_marker_also_matches_the_summary():
    matches = [match("log-x", "Repeated SSH brute force attempts")]
    assert hit_rank(matches, "brute force") == 1


def test_marker_matching_is_case_insensitive():
    assert hit_rank([match("DATA TLB error interrupt")], "data tlb") == 1


def test_no_match_has_no_rank():
    assert hit_rank([match("Disk full")], "kafka") is None


def test_score_reports_hit_at_1_hit_at_3_and_routing_separately():
    results = [
        {"rank": 1, "kind": "when", "expected_kind": "when"},
        {"rank": 3, "kind": "what", "expected_kind": "what"},
        {"rank": None, "kind": "what", "expected_kind": "count"},
        {"rank": 5, "kind": "count", "expected_kind": "count"},
    ]
    card = score(results)
    assert card["questions"] == 4
    assert card["hit_at_1"] == 0.25
    assert card["hit_at_3"] == 0.5
    assert card["routing_accuracy"] == 0.75
