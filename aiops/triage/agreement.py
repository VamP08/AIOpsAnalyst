"""Cohen's kappa: agreement between two raters corrected for chance.

kappa = (po - pe) / (1 - pe), where po is observed agreement and pe the
agreement expected if both raters labeled at random with their own marginal
frequencies. The M3 gate records this between hand labels and LLM verdicts
before any prompt tuning. When pe = 1 (both raters used a single category),
kappa is defined here as 1.0 for identical labels rather than 0/0.
"""
from collections import Counter


def cohens_kappa(a: list[str], b: list[str]) -> float:
    if len(a) != len(b):
        raise ValueError(f"label lists differ in length: {len(a)} vs {len(b)}")
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    freq_a, freq_b = Counter(a), Counter(b)
    pe = sum(freq_a[c] * freq_b.get(c, 0) for c in freq_a) / (n * n)
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)
