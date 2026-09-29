from aiops.envelope import Event
from aiops.triage.prompts import PROMPT_VERSION, build_messages
from aiops.triage.schema import CATEGORIES


def make_samples():
    return [Event(id=f"e{i}", source="s", type="dev.aiops.log.line",
                  title=f"Failed password for root from 10.0.0.{i}")
            for i in range(3)]


def test_messages_carry_taxonomy_label_and_samples():
    messages = build_messages("Failed password for <*> from <*>", "log",
                              make_samples())
    system, user = messages[0]["content"], messages[1]["content"]
    for category in CATEGORIES:
        assert category in system
    assert "Failed password for <*> from <*>" in user
    assert "e0" in user and "e2" in user


def test_system_prompt_is_stable_across_clusters():
    a = build_messages("template A", "log", make_samples())[0]["content"]
    b = build_messages("template B", "prose", make_samples())[0]["content"]
    assert a == b  # cacheable prefix: volatile payload stays in the user turn


def test_prompt_version_is_stamped():
    assert PROMPT_VERSION == "1.1"


def test_issue_template_boilerplate_never_reaches_the_model():
    issue = Event(id="i1", source="g", type="com.github.issue",
                  title="Middleware blocks the event loop",
                  body="### Submission checklist\n- [x] This is a bug\n\n"
                       "### Description\ncount_tokens runs synchronously")
    user = build_messages("Middleware blocks the event loop", "prose",
                          [issue])[1]["content"]
    assert "[x]" not in user and "Submission checklist" not in user
    assert "count_tokens runs synchronously" in user


def test_ground_truth_attributes_never_reach_the_model():
    event = Event(id="b1", source="bgl://llnl", type="dev.aiops.log.line",
                  title="data TLB error interrupt",
                  attributes={"bgl_label": "KERNDTLB", "node": "R20-M0"})
    messages = build_messages("data TLB error interrupt", "log", [event])
    prompt = messages[0]["content"] + messages[1]["content"]
    assert "KERNDTLB" not in prompt


def test_candidate_prompt_adds_boundary_rules_without_touching_the_default():
    from aiops.triage.prompts import CANDIDATE_VERSION, SYSTEMS

    assert PROMPT_VERSION == "1.1"          # 1.2 won its half and lost overall
    assert CANDIDATE_VERSION == "1.2"
    base = SYSTEMS["1.1"]
    candidate = SYSTEMS[CANDIDATE_VERSION]
    assert base in candidate.replace(
        candidate[candidate.index("Boundary rules"):candidate.index(
            "Do not guess")], "")
    for rule in ("never noise", "worded as a question", "phrased as a wish"):
        assert rule in candidate
        assert rule not in base


def test_build_messages_uses_the_requested_version():
    samples = make_samples()
    current = build_messages("t", "log", samples)[0]["content"]
    candidate = build_messages("t", "log", samples, version="1.2")[0]["content"]
    assert current != candidate
    assert "Boundary rules" not in current    # 1.1 is in use
    assert "Boundary rules" in candidate      # 1.2 kept so it can be rerun
