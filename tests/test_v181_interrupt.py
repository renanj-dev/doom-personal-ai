from app.cancellation import CancellationRegistry


def test_cancellation_registry_roundtrip():
    reg = CancellationRegistry(ttl_seconds=60)
    reg.start("req-1", "main")
    assert not reg.is_cancelled("req-1")
    assert reg.cancel("req-1", "main") is True
    assert reg.is_cancelled("req-1") is True
    assert reg.cancel("req-1", "other") is False
    reg.finish("req-1")
    assert not reg.is_cancelled("req-1")
