import json

from shared.services.taxi_router import config
from shared.services.taxi_router.hmi_chat import (
    format_readback_rejected,
    publish_pilot_message,
)


class _FakeRedis:
    def __init__(self):
        self.published: list[tuple[str, str]] = []
        self.setex_calls: list[tuple[str, int, str]] = []
        self.rpush_calls: list[tuple[str, str]] = []

    def publish(self, channel, message):
        self.published.append((channel, message))

    def setex(self, key, ttl, value):
        self.setex_calls.append((key, ttl, value))

    def rpush(self, key, value):
        self.rpush_calls.append((key, value))


def test_format_readback_rejected_template():
    text = format_readback_rejected("IBE3421", "taxiway Z not found")
    assert text == "IBE3421, unable, taxiway Z not found. Request alternative."


def test_publish_pilot_message_emits_chat_and_sets_last_error():
    r = _FakeRedis()
    publish_pilot_message(
        r,
        callsign="IBE3421",
        registration="EC-IYV",
        kind="readback_rejected",
        text="unable, taxiway Z not found",
        session_id="sess-1",
    )

    assert len(r.published) == 1
    channel, payload = r.published[0]
    assert channel == config.HMI_CHAT_CHANNEL
    obj = json.loads(payload)
    assert obj["callsign"] == "IBE3421"
    assert obj["registration"] == "EC-IYV"
    assert obj["kind"] == "readback_rejected"
    assert obj["sender"] == "pilot"
    assert obj["session_id"] == "sess-1"
    assert "text" in obj and obj["text"]

    assert len(r.setex_calls) == 1
    key, ttl, _val = r.setex_calls[0]
    assert key == config.LAST_ERROR_KEY.format(registration="EC-IYV")
    assert ttl == config.LAST_ERROR_TTL_S
