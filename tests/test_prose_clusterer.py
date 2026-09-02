from aiops.cluster.prose import ProseClusterer
from aiops.envelope import Event

CRASH_A = "App crashes on startup when the config file is empty. Traceback in loader."
CRASH_A_DUP = "App crashes on startup when the config file is empty! Traceback in loader"
CRASH_PARAPHRASE = "Empty configuration makes the application fail at boot with a loader stacktrace"
FEATURE = "Please add dark mode to the settings screen"

VECTORS = {
    CRASH_A: [1.0, 0.0, 0.0],
    CRASH_A_DUP: [1.0, 0.0, 0.0],
    CRASH_PARAPHRASE: [0.95, 0.3, 0.05],
    FEATURE: [0.0, 0.0, 1.0],
}


def fake_encoder(texts):
    return [VECTORS[t] for t in texts]


def make_events(texts):
    return [Event(id=f"i{n}", source="github://acme/widget",
                  type="com.github.issue", title=t)
            for n, t in enumerate(texts)]


def test_near_duplicates_and_paraphrases_share_a_cluster():
    clusterer = ProseClusterer(encoder=fake_encoder, threshold=0.8)
    assignment = clusterer.assign(
        make_events([CRASH_A, CRASH_A_DUP, CRASH_PARAPHRASE, FEATURE]))
    assert assignment["i0"] == assignment["i1"]  # lexical near-dup (MinHash)
    assert assignment["i0"] == assignment["i2"]  # semantic (embedding edge)
    assert assignment["i3"] != assignment["i0"]


def test_assignment_is_deterministic():
    events = make_events([CRASH_A, CRASH_A_DUP, CRASH_PARAPHRASE, FEATURE])
    a = ProseClusterer(encoder=fake_encoder).assign(events)
    b = ProseClusterer(encoder=fake_encoder).assign(events)
    assert a == b


def test_title_and_body_both_feed_the_text():
    seen = []

    def spy_encoder(texts):
        seen.extend(texts)
        return [[1.0, 0.0, 0.0] for _ in texts]

    events = [Event(id="i0", source="s", type="com.github.issue",
                    title="Crash on save", body="Stack trace: ...")]
    ProseClusterer(encoder=spy_encoder).assign(events)
    assert any("Crash on save" in t and "Stack trace" in t for t in seen)


def test_singleton_events_get_their_own_clusters():
    events = make_events([CRASH_A, FEATURE])
    assignment = ProseClusterer(encoder=fake_encoder).assign(events)
    assert assignment["i0"] != assignment["i1"]
