import pytest

from aiops.ask import answer, classify
from aiops.envelope import Event
from aiops.store import Store


@pytest.fixture
def store(tmp_path):
    store = Store(str(tmp_path / "t.sqlite"))
    ssh = [Event(id=f"s{i}", source="syslog://web-1", type="dev.aiops.log.line",
                 title=f"Failed password for root from 10.0.0.{i}",
                 time=f"2026-09-0{i + 1}T10:00:00")
           for i in range(3)]
    disk = [Event(id="d1", source="syslog://web-1", type="dev.aiops.log.line",
                  title="Disk full on /dev/sda1", time="2026-09-05T09:00:00")]
    store.insert_events([*ssh, *disk])
    store.assign_clusters(
        {**{e.id: "log-ssh" for e in ssh}, "d1": "log-disk"},
        {"log-ssh": ("Failed password for <*> from <*>", "log"),
         "log-disk": ("Disk full on <*>", "log")})
    store.upsert_verdict("log-ssh", {
        "category": "error", "severity": "medium",
        "summary": "Repeated SSH authentication failures against root",
        "confidence": 0.92, "evidence": ["s0"], "tier": "auto",
        "model": "m", "promptversion": "1.1"})
    return store


@pytest.mark.parametrize("question,kind", [
    ("when did the ssh failures start", "when"),
    ("When did checkout errors begin?", "when"),
    ("how many password failures were there", "count"),
    ("count the disk problems", "count"),
    ("what is failing on the web server", "what"),
    ("ssh", "what"),
])
def test_question_kind_is_recognised(question, kind):
    assert classify(question) == kind


def test_when_question_is_answered_from_timestamps_not_prose(store):
    result = answer(store, "when did the password failures start?")
    assert result["kind"] == "when"
    assert result["cluster"]["id"] == "log-ssh"
    assert result["first"] == "2026-09-01T10:00:00"
    assert result["last"] == "2026-09-03T10:00:00"


def test_count_question_sums_events_in_matching_clusters(store):
    result = answer(store, "how many password failures were there?")
    assert result["kind"] == "count"
    assert result["events"] == 3
    assert result["clusters"] == 1


def test_what_question_returns_ranked_clusters_with_their_verdicts(store):
    result = answer(store, "ssh authentication")
    assert result["kind"] == "what"
    assert result["matches"][0]["id"] == "log-ssh"
    assert result["matches"][0]["category"] == "error"
    assert result["matches"][0]["summary"].startswith("Repeated SSH")


def test_every_answer_carries_evidence_events(store):
    result = answer(store, "when did the password failures start?")
    assert any("Failed password for root" in e["title"] for e in result["evidence"])


def test_a_question_that_matches_nothing_says_so_rather_than_guessing(store):
    result = answer(store, "kubernetes ingress certificate rotation")
    assert result["kind"] == "none"
    assert result["matches"] == []


def test_embeddings_find_a_cluster_whose_words_never_appear(store):
    # "brute force" is in a summary; "intrusion" is in neither label nor
    # summary, so only a semantic pass can reach it
    vectors = {
        "intrusion attempts": [1.0, 0.0],
        "Failed password for <*> from <*> Repeated SSH authentication "
        "failures against root": [0.96, 0.28],
        "Disk full on <*> ": [0.0, 1.0],
    }

    def encoder(texts):
        return [vectors.get(t.strip(), [0.0, 0.0]) for t in texts]

    lexical = answer(store, "intrusion attempts", encoder=False)
    assert lexical["kind"] == "none"     # no shared vocabulary to match on

    hybrid = answer(store, "intrusion attempts", encoder=encoder)
    assert hybrid["matches"][0]["id"] == "log-ssh"
    assert hybrid["matches"][0]["how"] == "semantic"


def test_lexical_hits_keep_their_place_ahead_of_semantic_ones(store):
    def encoder(texts):
        return [[1.0, 0.0] for _ in texts]        # everything looks identical

    result = answer(store, "password", encoder=encoder)
    assert result["matches"][0]["id"] == "log-ssh"
    assert result["matches"][0]["how"] == "lexical"


def test_semantic_keeps_slots_even_when_lexical_fills_the_page(store):
    # a bag of common words matches many clusters weakly; the semantic pass
    # must still get a seat, which is the whole reason it exists
    def encoder(texts):
        return [[1.0, 0.0] if "Disk full" in t else [0.0, 1.0] for t in texts]

    result = answer(store, "what is going on", limit=2, encoder=encoder)
    hows = [m["how"] for m in result["matches"]]
    assert "semantic" in hows
