import pytest

from aiops.registry import Source, Sink, register, create, SOURCES, SINKS


@register("fake_source")
class FakeSource(Source):
    def __init__(self, path="default"):
        self.path = path

    def fetch(self, cursor=None):
        return iter(())


@register("fake_sink")
class FakeSink(Sink):
    def __init__(self, channel="general"):
        self.channel = channel
        self.emitted = []

    def emit(self, decision):
        self.emitted.append(decision)


def test_register_puts_source_and_sink_in_their_registries():
    assert SOURCES["fake_source"] is FakeSource
    assert SINKS["fake_sink"] is FakeSink


def test_create_instantiates_by_name_with_config_kwargs():
    src = create("fake_source", {"path": "/var/log/nginx"})
    assert isinstance(src, FakeSource)
    assert src.path == "/var/log/nginx"


def test_create_unknown_name_raises_with_known_names_listed():
    with pytest.raises(KeyError, match="fake_source"):
        create("nope", {})


def test_source_check_defaults_to_true():
    assert FakeSource().check() is True


def test_registering_duplicate_name_raises():
    with pytest.raises(ValueError, match="fake_source"):
        @register("fake_source")
        class Duplicate(Source):
            def fetch(self, cursor=None):
                return iter(())
