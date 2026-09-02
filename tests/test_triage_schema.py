from aiops.triage.schema import Verdict, parse_verdict

GOOD = ('{"category": "crash", "severity": "high", '
        '"summary": "Login worker dies on empty config", '
        '"confidence": 0.82, "evidence": ["e1", "e2"]}')


def test_valid_json_parses_to_verdict():
    v = parse_verdict(GOOD)
    assert isinstance(v, Verdict)
    assert v.category == "crash"
    assert v.severity == "high"
    assert v.confidence == 0.82
    assert v.evidence == ["e1", "e2"]


def test_json_wrapped_in_prose_or_fences_still_parses():
    assert parse_verdict(f"Here is the answer:\n```json\n{GOOD}\n```") is not None


def test_unknown_category_rejected():
    bad = GOOD.replace("crash", "banana")
    assert parse_verdict(bad) is None


def test_confidence_out_of_bounds_rejected():
    assert parse_verdict(GOOD.replace("0.82", "1.7")) is None


def test_garbage_returns_none():
    assert parse_verdict("the model rambled with no json") is None
    assert parse_verdict("") is None
