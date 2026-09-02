"""Grouping Accuracy as defined by the LogPai logparser benchmark.

A line counts as correctly grouped only when its predicted cluster contains
exactly the same set of lines as its ground-truth template. Splits and merges
therefore fail every line involved — stricter and more honest than pairwise
agreement.
"""
from collections import defaultdict


def grouping_accuracy(predicted: dict[str, str], truth: dict[str, str]) -> float:
    by_predicted = defaultdict(set)
    by_truth = defaultdict(set)
    for line, cluster in predicted.items():
        by_predicted[cluster].add(line)
    for line, template in truth.items():
        by_truth[template].add(line)
    correct = sum(len(lines) for lines in by_predicted.values()
                  if lines in by_truth.values())
    return correct / len(predicted) if predicted else 0.0
