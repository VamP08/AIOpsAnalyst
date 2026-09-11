import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

from harvest_maintainer_labels import collapse_model, harvest, map_labels

from aiops.envelope import Event
from aiops.store import Store


def test_signal_labels_map_to_collapsed_classes():
    assert map_labels({"bug"}) == "defect"
    assert map_labels({"kind/bug", "triaged"}) == "defect"
    assert map_labels({"feature request"}) == "feature_request"
    assert map_labels({"kind/feature"}) == "feature_request"
    assert map_labels({"question"}) == "question"
    assert map_labels({"performance"}) == "performance"


def test_labels_carrying_no_signal_are_unusable():
    assert map_labels({"locked", "external", "bot-triaged"}) is None
    assert map_labels(set()) is None


def test_two_signal_classes_are_excluded_rather_than_guessed():
    assert map_labels({"bug", "kind/feature"}) is None


def test_mapping_is_case_insensitive():
    assert map_labels({"Feature request"}) == "feature_request"
    assert map_labels({"BUG"}) == "defect"


def test_model_categories_collapse_to_the_same_space():
    assert collapse_model("crash") == "defect"
    assert collapse_model("error") == "defect"
    assert collapse_model("performance") == "performance"
    assert collapse_model("feature_request") == "feature_request"
    assert collapse_model("question") == "question"
    assert collapse_model("noise") == "noise"


def issue(event_id, cluster, labels, url="https://example.com/1"):
    return Event(id=event_id, source="github://acme/widget",
                 type="com.github.issue", title=f"issue {event_id}", url=url,
                 attributes={"labels": labels})


def test_harvest_returns_one_row_per_usable_cluster(tmp_path):
    store = Store(str(tmp_path / "db.sqlite"))
    store.insert_events([
        issue("i1", "prose-a", "bug,locked"),
        issue("i2", "prose-a", "bug"),
        issue("i3", "prose-b", "kind/feature"),
        issue("i4", "prose-c", "locked"),            # no signal
        issue("i5", "prose-d", "bug"),
        issue("i6", "prose-d", "kind/feature"),      # disagrees with i5
    ])
    store.assign_clusters(
        {"i1": "prose-a", "i2": "prose-a", "i3": "prose-b",
         "i4": "prose-c", "i5": "prose-d", "i6": "prose-d"},
        {c: (f"label {c}", "prose") for c in
         ("prose-a", "prose-b", "prose-c", "prose-d")})

    rows = {r["clusterid"]: r for r in harvest(store)}
    assert set(rows) == {"prose-a", "prose-b"}
    assert rows["prose-a"]["category"] == "defect"
    assert "bug" in rows["prose-a"]["source_labels"]
    assert rows["prose-a"]["url"] == "https://example.com/1"
    assert rows["prose-b"]["category"] == "feature_request"


def test_harvest_ignores_log_clusters(tmp_path):
    store = Store(str(tmp_path / "db.sqlite"))
    store.insert_events([Event(id="l1", source="s", type="dev.aiops.log.line",
                               title="a log line")])
    store.assign_clusters({"l1": "log-a"}, {"log-a": ("a log line", "log")})
    assert harvest(store) == []
