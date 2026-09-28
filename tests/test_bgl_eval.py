import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

from bgl_report import is_alert, surfaced, tally

from aiops.envelope import Event


def test_operator_label_dash_means_routine():
    assert is_alert("-") is False
    assert is_alert("KERNDTLB") is True
    assert is_alert("APPREAD") is True


def test_a_line_is_surfaced_when_its_cluster_is_not_noise():
    assert surfaced("error") is True
    assert surfaced("crash") is True
    assert surfaced("performance") is True
    assert surfaced("noise") is False
    assert surfaced(None) is False        # untriaged surfaces nothing


def test_tally_counts_the_four_outcomes_at_line_level():
    lines = [("-", "noise"), ("-", "noise"), ("-", "error"),
             ("KERNDTLB", "error"), ("KERNRTSP", "noise")]
    counts = tally(lines)
    assert counts == {"alert_surfaced": 1, "alert_missed": 1,
                      "routine_surfaced": 1, "routine_suppressed": 2}


def test_tally_on_an_empty_corpus_is_all_zero():
    assert tally([]) == {"alert_surfaced": 0, "alert_missed": 0,
                         "routine_surfaced": 0, "routine_suppressed": 0}
