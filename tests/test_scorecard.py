import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

from agreement_report import scorecard

HUMAN = ["error", "error", "noise", "crash", "error"]
MODEL = ["error", "noise", "noise", "crash", "error"]
PROVENANCE = [("1.1", "gpt-oss-120b")] * 4 + [("1.1", "qwen3.8-27b")]


def test_scorecard_counts_pairs_agreement_and_kappa():
    card = scorecard(HUMAN, MODEL, PROVENANCE)
    assert card["pairs"] == 5
    assert card["raw_agreement"] == 0.8
    assert 0.0 < card["cohens_kappa"] < 1.0


def test_per_category_precision_and_recall_use_support_not_totals():
    card = scorecard(HUMAN, MODEL, PROVENANCE)["per_category"]
    assert card["error"]["support"] == 3
    assert card["error"]["precision"] == 1.0        # 2 predicted, 2 right
    assert round(card["error"]["recall"], 2) == 0.67  # 2 of 3 found
    assert card["noise"]["precision"] == 0.5        # 2 predicted, 1 right
    assert card["performance"]["support"] == 0
    assert card["performance"]["precision"] is None  # never predicted


def test_confusions_and_provenance_are_reported():
    card = scorecard(HUMAN, MODEL, PROVENANCE)
    assert card["confusions"] == {"error -> noise": 1}
    assert card["prompt_versions"] == ["1.1"]
    assert card["models"] == {"gpt-oss-120b": 4, "qwen3.8-27b": 1}
