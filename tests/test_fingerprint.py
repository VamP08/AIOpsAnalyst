from aiops.cluster.fingerprint import compute_fingerprint
from aiops.envelope import Event


def make_alert(**overrides):
    fields = dict(
        id="a1",
        source="webhook://alertmanager",
        type="dev.aiops.alert",
        title="HighErrorRate",
        attributes={"alertname": "HighErrorRate", "service": "checkout",
                    "instance": "10.0.0.7:9090"},
    )
    fields.update(overrides)
    return Event(**fields)


def test_same_key_fields_same_fingerprint():
    a = compute_fingerprint(make_alert(id="a1"),
                            fields=("attributes.alertname", "attributes.service"))
    b = compute_fingerprint(make_alert(id="a2"),
                            fields=("attributes.alertname", "attributes.service"))
    assert a == b
    assert len(a) == 16


def test_different_service_different_fingerprint():
    a = compute_fingerprint(make_alert(),
                            fields=("attributes.alertname", "attributes.service"))
    other = make_alert(attributes={"alertname": "HighErrorRate",
                                   "service": "payments"})
    b = compute_fingerprint(other,
                            fields=("attributes.alertname", "attributes.service"))
    assert a != b


def test_noisy_fields_excluded_by_key_choice():
    # instance differs; fingerprint on alertname+service must not care
    noisy = make_alert(attributes={"alertname": "HighErrorRate",
                                   "service": "checkout",
                                   "instance": "10.0.0.99:9090"})
    a = compute_fingerprint(make_alert(),
                            fields=("attributes.alertname", "attributes.service"))
    b = compute_fingerprint(noisy,
                            fields=("attributes.alertname", "attributes.service"))
    assert a == b


def test_missing_field_contributes_empty_not_crash():
    bare = make_alert(attributes={})
    fp = compute_fingerprint(bare, fields=("attributes.alertname", "title"))
    assert isinstance(fp, str) and len(fp) == 16


def test_top_level_fields_work():
    a = compute_fingerprint(make_alert(), fields=("source", "title"))
    b = compute_fingerprint(make_alert(title="OtherAlert"),
                            fields=("source", "title"))
    assert a != b
