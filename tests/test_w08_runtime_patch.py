from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

pytest.importorskip("gateway", reason="requires Hermes gateway")

from gateway.config import HomeChannel, Platform  # noqa: E402
from gateway.platform_registry import PlatformEntry, platform_registry  # noqa: E402
from gateway.platforms.base import SendResult  # noqa: E402

from hermes_seatalk import adapter as seatalk_adapter  # noqa: E402

pytestmark = pytest.mark.requires_hermes


def _register_platform_entry():
    platform_registry.register(PlatformEntry(
        name="seatalk",
        label="SeaTalk",
        adapter_factory=lambda cfg: seatalk_adapter.SeaTalkAdapter(cfg),
        check_fn=lambda: True,
        max_message_length=4000,
        allowed_users_env="HERMES_SEATALK_ALLOWED_USERS",
    ))
    return Platform("seatalk")


class FakeRuntimeAdapter:
    def __init__(self):
        self.calls = []

    async def send(self, chat_id, content, metadata=None):
        self.calls.append(("text", chat_id, content, metadata))
        return SendResult(success=True, message_id=f"m-{len(self.calls)}")

    async def send_image_file(self, chat_id, image_path, caption="", metadata=None):
        self.calls.append(("image", chat_id, image_path, caption, metadata))
        return SendResult(success=True, message_id=f"m-{len(self.calls)}")

    async def send_document(self, chat_id, file_path, caption="", metadata=None):
        self.calls.append(("document", chat_id, file_path, caption, metadata))
        return SendResult(success=True, message_id=f"m-{len(self.calls)}")


def test_t08_08_target_parser_full_formats(monkeypatch):
    import tools.send_message_tool as send_message_tool

    original = getattr(send_message_tool._parse_target_ref, "_seatalk_original", send_message_tool._parse_target_ref)
    monkeypatch.setattr(send_message_tool, "_parse_target_ref", original)
    seatalk_adapter._patch_send_message_tool()

    parse = send_message_tool._parse_target_ref
    assert parse("seatalk", "EmpABC") == ("EmpABC", None, True)
    assert parse("seatalk", "Alice@Example.com") == ("alice@example.com", None, True)
    assert parse("seatalk", "group/GroupABC") == ("group/GroupABC", None, True)
    assert parse("seatalk", "alice@example.com:ThreadXYZ") == ("alice@example.com", "ThreadXYZ", True)
    assert parse("seatalk", "EmpABC:ThreadXYZ") == ("EmpABC", "ThreadXYZ", True)
    assert parse("seatalk", "group/GroupABC:ThreadXYZ") == ("group/GroupABC", "ThreadXYZ", True)


def test_t08_03_home_channel(monkeypatch):
    from gateway.config import GatewayConfig

    platform = _register_platform_entry()
    original = getattr(GatewayConfig.get_home_channel, "_seatalk_original", GatewayConfig.get_home_channel)
    monkeypatch.setattr(GatewayConfig, "get_home_channel", original)
    monkeypatch.setenv("SEATALK_HOME_CHANNEL", "group/Home")

    seatalk_adapter._patch_home_channel()
    cfg = GatewayConfig.__new__(GatewayConfig)
    cfg.platforms = {
        platform: SimpleNamespace(home_channel=None, extra={})
    }

    home = cfg.get_home_channel(platform)

    assert home.chat_id == "group/Home"
    assert home.name == "SeaTalk Home"
    assert home.thread_id is None


def test_t08_04_home_thread_id(monkeypatch):
    from gateway.config import GatewayConfig

    platform = _register_platform_entry()
    original = getattr(GatewayConfig.get_home_channel, "_seatalk_original", GatewayConfig.get_home_channel)
    monkeypatch.setattr(GatewayConfig, "get_home_channel", original)
    monkeypatch.setenv("SEATALK_HOME_CHANNEL", "group/Home")
    monkeypatch.setenv("SEATALK_HOME_CHANNEL_THREAD_ID", "ThreadHome")

    seatalk_adapter._patch_home_channel()
    cfg = GatewayConfig.__new__(GatewayConfig)
    cfg.platforms = {
        platform: SimpleNamespace(home_channel=None, extra={})
    }

    home = cfg.get_home_channel(platform)

    assert home.chat_id == "group/Home"
    assert home.thread_id == "ThreadHome"


def test_t08_09_home_channel_legacy_without_thread_id():
    class LegacyHomeChannel:
        def __init__(self, *, platform, chat_id, name):
            self.platform = platform
            self.chat_id = chat_id
            self.name = name

    home = seatalk_adapter._make_home_channel(
        LegacyHomeChannel,
        platform="seatalk",
        chat_id="staging:group/Home",
        name="SeaTalk Home",
        thread_id="ThreadHome",
    )

    assert home.chat_id == "staging:group/Home"
    assert home.name == "SeaTalk Home"
    assert not hasattr(home, "thread_id")


@pytest.mark.asyncio
async def test_t08_02_send_to_platform_supports_seatalk(monkeypatch, tmp_path):
    import gateway.run as gateway_run

    platform = _register_platform_entry()
    runtime_adapter = FakeRuntimeAdapter()
    monkeypatch.setattr(
        gateway_run,
        "_gateway_runner_ref",
        lambda: SimpleNamespace(adapters={platform: runtime_adapter}),
    )
    image = tmp_path / "photo.png"
    image.write_bytes(b"image")
    document = tmp_path / "report.txt"
    document.write_text("document")

    result = await seatalk_adapter._seatalk_send_to_platform(
        platform,
        "group/GroupABC",
        "hello",
        thread_id="ThreadXYZ",
        media_files=[(str(image), False), (str(document), False)],
    )

    assert result == {"success": True, "message_id": "m-3"}
    assert runtime_adapter.calls[0] == ("text", "group/GroupABC", "hello", {"thread_id": "ThreadXYZ"})
    assert runtime_adapter.calls[1][0] == "image"
    assert runtime_adapter.calls[2][0] == "document"


def test_t08_01_send_message_supports_seatalk(monkeypatch):
    import gateway.config as gateway_config
    import gateway.run as gateway_run
    import tools.send_message_tool as send_message_tool

    platform = _register_platform_entry()
    original_parse = getattr(send_message_tool._parse_target_ref, "_seatalk_original", send_message_tool._parse_target_ref)
    original_send = getattr(send_message_tool._send_to_platform, "_seatalk_original", send_message_tool._send_to_platform)
    monkeypatch.setattr(send_message_tool, "_parse_target_ref", original_parse)
    monkeypatch.setattr(send_message_tool, "_send_to_platform", original_send)
    seatalk_adapter._patch_send_message_tool()
    seatalk_adapter._patch_send_to_platform()

    runtime_adapter = FakeRuntimeAdapter()
    monkeypatch.setattr(
        gateway_run,
        "_gateway_runner_ref",
        lambda: SimpleNamespace(adapters={platform: runtime_adapter}),
    )
    fake_config = SimpleNamespace(
        platforms={platform: SimpleNamespace(enabled=True, extra={})},
        get_home_channel=lambda requested: HomeChannel(
            platform=requested,
            chat_id="group/Home",
            name="SeaTalk Home",
            thread_id="ThreadHome",
        ),
    )
    monkeypatch.setattr(gateway_config, "load_gateway_config", lambda: fake_config)

    result = json.loads(send_message_tool._handle_send({
        "target": "seatalk",
        "message": "hello",
    }))

    assert result["success"] is True
    assert result["note"] == "Sent to seatalk home channel (chat_id: group/Home)"
    assert runtime_adapter.calls == [("text", "group/Home", "hello", None)]


def test_t08_05_cron_target(monkeypatch):
    import cron.scheduler as scheduler

    monkeypatch.setattr(scheduler, "_KNOWN_DELIVERY_PLATFORMS", frozenset({"telegram"}))
    monkeypatch.setattr(scheduler, "_HOME_TARGET_ENV_VARS", {"telegram": "TELEGRAM_HOME_CHANNEL"})
    monkeypatch.setenv("SEATALK_HOME_CHANNEL", "group/Home")

    seatalk_adapter._patch_cron_scheduler()

    assert "seatalk" in scheduler._KNOWN_DELIVERY_PLATFORMS
    assert scheduler._resolve_single_delivery_target({}, "seatalk") == {
        "platform": "seatalk",
        "chat_id": "group/Home",
        "thread_id": None,
    }


def test_t08_06_patch_idempotent(monkeypatch):
    import tools.send_message_tool as send_message_tool
    from gateway.config import GatewayConfig

    original_parse = getattr(send_message_tool._parse_target_ref, "_seatalk_original", send_message_tool._parse_target_ref)
    original_send = getattr(send_message_tool._send_to_platform, "_seatalk_original", send_message_tool._send_to_platform)
    original_home = getattr(GatewayConfig.get_home_channel, "_seatalk_original", GatewayConfig.get_home_channel)
    monkeypatch.setattr(send_message_tool, "_parse_target_ref", original_parse)
    monkeypatch.setattr(send_message_tool, "_send_to_platform", original_send)
    monkeypatch.setattr(GatewayConfig, "get_home_channel", original_home)

    seatalk_adapter._patch_send_message_tool()
    seatalk_adapter._patch_send_to_platform()
    seatalk_adapter._patch_home_channel()
    once = (
        send_message_tool._parse_target_ref,
        send_message_tool._send_to_platform,
        GatewayConfig.get_home_channel,
    )
    seatalk_adapter._patch_send_message_tool()
    seatalk_adapter._patch_send_to_platform()
    seatalk_adapter._patch_home_channel()

    assert once == (
        send_message_tool._parse_target_ref,
        send_message_tool._send_to_platform,
        GatewayConfig.get_home_channel,
    )


def test_t08_07_builtin_platform_regression(monkeypatch):
    import tools.send_message_tool as send_message_tool

    original = getattr(send_message_tool._parse_target_ref, "_seatalk_original", send_message_tool._parse_target_ref)
    monkeypatch.setattr(send_message_tool, "_parse_target_ref", original)
    seatalk_adapter._patch_send_message_tool()

    assert send_message_tool._parse_target_ref("slack", "C12345678") == ("C12345678", None, True)
    assert send_message_tool._parse_target_ref("discord", "123456789:987654321") == (
        "123456789",
        "987654321",
        True,
    )
