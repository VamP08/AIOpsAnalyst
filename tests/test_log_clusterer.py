from aiops.cluster.drain import LogClusterer
from aiops.envelope import Event


def make_events(lines):
    return [Event(id=f"e{i}", source="s", type="dev.aiops.log.line",
                  title=line, raw=line)
            for i, line in enumerate(lines)]


LINES = [
    "Connection timeout to 10.0.0.5 after 30s",
    "Connection timeout to 10.0.0.9 after 12s",
    "Disk full on /dev/sda1",
    "Connection timeout to 10.0.0.7 after 45s",
]


def test_structurally_similar_lines_share_a_cluster():
    assignment = LogClusterer().assign(make_events(LINES))
    assert assignment["e0"] == assignment["e1"] == assignment["e3"]
    assert assignment["e2"] != assignment["e0"]


def test_assignment_is_deterministic_across_fresh_runs():
    a = LogClusterer().assign(make_events(LINES))
    b = LogClusterer().assign(make_events(LINES))
    assert a == b


def test_templates_mask_variable_parts_and_sizes_are_tracked():
    clusterer = LogClusterer()
    assignment = clusterer.assign(make_events(LINES))
    clusters = {cid: (template, size)
                for cid, template, size in clusterer.clusters()}
    template, size = clusters[assignment["e0"]]
    assert "<*>" in template
    assert "Connection timeout" in template
    assert size == 3
    assert clusters[assignment["e2"]][1] == 1
