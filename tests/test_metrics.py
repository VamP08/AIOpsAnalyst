from aiops.cluster.metrics import grouping_accuracy


def test_perfect_grouping_scores_one():
    predicted = {"l1": "a", "l2": "a", "l3": "b"}
    truth = {"l1": "E1", "l2": "E1", "l3": "E2"}
    assert grouping_accuracy(predicted, truth) == 1.0


def test_split_cluster_fails_all_its_lines():
    # ground truth says l1-l3 are one template; prediction split them
    predicted = {"l1": "a", "l2": "a", "l3": "b", "l4": "c"}
    truth = {"l1": "E1", "l2": "E1", "l3": "E1", "l4": "E2"}
    # l1,l2,l3 wrong (their predicted sets don't equal the truth set), l4 right
    assert grouping_accuracy(predicted, truth) == 0.25


def test_merged_clusters_fail_both_sides():
    predicted = {"l1": "a", "l2": "a"}
    truth = {"l1": "E1", "l2": "E2"}
    assert grouping_accuracy(predicted, truth) == 0.0
