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
    assert PROMPT_VERSION == "1.0"
