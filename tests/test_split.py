import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

from split import split_labels


ROWS = [{"clusterid": f"c{i}", "category": "defect" if i % 3 else "feature_request"}
        for i in range(40)]


def test_split_is_deterministic_for_a_seed():
    assert split_labels(ROWS, seed=7) == split_labels(ROWS, seed=7)


def test_a_different_seed_gives_a_different_split():
    assert split_labels(ROWS, seed=7) != split_labels(ROWS, seed=8)


def test_every_row_lands_in_exactly_one_side():
    dev, test = split_labels(ROWS, seed=7)
    ids = [r["clusterid"] for r in dev] + [r["clusterid"] for r in test]
    assert sorted(ids) == sorted(r["clusterid"] for r in ROWS)
    assert len(set(ids)) == len(ROWS)


def test_both_sides_keep_the_class_balance():
    dev, test = split_labels(ROWS, seed=7)
    share = lambda rows: sum(r["category"] == "defect" for r in rows) / len(rows)
    assert abs(share(dev) - share(test)) < 0.15
