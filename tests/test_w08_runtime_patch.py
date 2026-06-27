from __future__ import annotations

import asyncio
import json
import threading
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


def test_t08_03_env_enablement_home_channel(monkeypatch):
    """The env-driven home channel replaces the get_home_channel patch.

    ``_seatalk_env_enablement`` returns a ``home_channel`` dict that the
    platform registry wires up as a proper ``HomeChannel`` on the
    ``PlatformConfig`` before adapter construction.
    """
    monkeypatch.delenv("SEATALK_HOME_CHANNEL_THREAD_ID", raising=False)
    monkeypatch.setenv("SEATALK_HOME_CHANNEL", "group/Home")

    seed = seatalk_adapter._seatalk_env_enablement()

    assert seed == {
        "home_channel": {
            "chat_id": "group/Home",
            "name": "SeaTalk Home",
            "thread_id": None,
        }
    }


def test_t08_04_env_enablement_home_thread_id(monkeypatch):
    monkeypatch.setenv("SEATALK_HOME_CHANNEL", "group/Home")
    monkeypatch.setenv("SEATALK_HOME_CHANNEL_THREAD_ID", "ThreadHome")
    monkeypatch.setenv("SEATALK_HOME_CHANNEL_NAME", "Ops")

    seed = seatalk_adapter._seatalk_env_enablement()

    assert seed["home_channel"]["chat_id"] == "group/Home"
    assert seed["home_channel"]["thread_id"] == "ThreadHome"
    assert seed["home_channel"]["name"] == "Ops"


def test_t08_09_env_enablement_unset_returns_none(monkeypatch):
    """No SEATALK_HOME_CHANNEL → no seed, so a YAML-configured home channel
    (read via the standard ``config.home_channel`` path) is left untouched."""
    monkeypatch.delenv("SEATALK_HOME_CHANNEL", raising=False)

    assert seatalk_adapter._seatalk_env_enablement() is None


def test_t08_10_env_enablement_registered_on_platform_entry():
    """register() must wire the env enablement hook so core can seed the
    home channel without the old GatewayConfig.get_home_channel patch."""
    captured = {}

    def fake_register_platform(**kwargs):
        captured.update(kwargs)

    ctx = SimpleNamespace(
        register_platform=fake_register_platform,
        register_tool=lambda **kw: None,
    )
    seatalk_adapter.register(ctx)

    assert captured.get("env_enablement_fn") is seatalk_adapter._seatalk_env_enablement
    assert captured.get("cron_deliver_env_var") == "SEATALK_HOME_CHANNEL"


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
    assert runtime_adapter.calls[0] == (
        "text",
        "group/GroupABC",
        "hello",
        {"_skip_coalescing": True, "thread_id": "ThreadXYZ"},
    )
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
    assert runtime_adapter.calls == [("text", "group/Home", "hello", {"_skip_coalescing": True})]


@pytest.mark.asyncio
async def test_t08_11_send_to_platform_accepts_force_document(monkeypatch):
    import gateway.run as gateway_run
    import tools.send_message_tool as send_message_tool

    platform = _register_platform_entry()
    original_send = getattr(send_message_tool._send_to_platform, "_seatalk_original", send_message_tool._send_to_platform)
    monkeypatch.setattr(send_message_tool, "_send_to_platform", original_send)
    seatalk_adapter._patch_send_to_platform()

    runtime_adapter = FakeRuntimeAdapter()
    monkeypatch.setattr(
        gateway_run,
        "_gateway_runner_ref",
        lambda: SimpleNamespace(adapters={platform: runtime_adapter}),
    )

    result = await send_message_tool._send_to_platform(
        platform,
        SimpleNamespace(extra={}),
        "group/Home",
        "hello",
        force_document=True,
    )

    assert result == {"success": True, "message_id": "m-1"}
    assert runtime_adapter.calls == [("text", "group/Home", "hello", {"_skip_coalescing": True})]


@pytest.mark.asyncio
async def test_t08_11b_force_document_routes_images_via_send_document(monkeypatch, tmp_path):
    """force_document=True must override image-extension routing so SeaTalk
    receives the file via send_document (preserves quality / file name)."""
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

    result = await seatalk_adapter._seatalk_send_to_platform(
        platform,
        "group/GroupABC",
        "",
        media_files=[(str(image), False)],
        force_document=True,
    )

    assert result["success"] is True
    assert len(runtime_adapter.calls) == 1
    assert runtime_adapter.calls[0][0] == "document", (
        f"force_document must override image routing; got {runtime_adapter.calls[0][0]}"
    )


@pytest.mark.asyncio
async def test_t08_11c_default_still_routes_images_via_send_image_file(monkeypatch, tmp_path):
    """Sanity: without force_document, image-extension files still go through
    send_image_file (we did not regress the default behavior)."""
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

    await seatalk_adapter._seatalk_send_to_platform(
        platform,
        "group/GroupABC",
        "",
        media_files=[(str(image), False)],
    )

    assert runtime_adapter.calls[0][0] == "image"


@pytest.mark.asyncio
async def test_t08_12_send_to_platform_uses_gateway_loop(monkeypatch):
    import gateway.run as gateway_run

    class LoopCapturingRuntimeAdapter(FakeRuntimeAdapter):
        async def send(self, chat_id, content, metadata=None):
            self.calls.append(("text", chat_id, content, metadata, asyncio.get_running_loop()))
            return SendResult(success=True, message_id=f"m-{len(self.calls)}")

    platform = _register_platform_entry()
    runtime_adapter = LoopCapturingRuntimeAdapter()
    gateway_loop = asyncio.new_event_loop()
    ready = threading.Event()

    def run_loop():
        asyncio.set_event_loop(gateway_loop)
        ready.set()
        gateway_loop.run_forever()

    thread = threading.Thread(target=run_loop)
    thread.start()
    ready.wait(timeout=2)
    try:
        monkeypatch.setattr(
            gateway_run,
            "_gateway_runner_ref",
            lambda: SimpleNamespace(adapters={platform: runtime_adapter}, _gateway_loop=gateway_loop),
        )

        result = await seatalk_adapter._seatalk_send_to_platform(platform, "EmpABC", "hello")

        assert result == {"success": True, "message_id": "m-1"}
        assert runtime_adapter.calls == [
            ("text", "EmpABC", "hello", {"_skip_coalescing": True}, gateway_loop)
        ]
    finally:
        gateway_loop.call_soon_threadsafe(gateway_loop.stop)
        thread.join(timeout=2)
        gateway_loop.close()


def test_t08_05_cron_target(monkeypatch):
    """SeaTalk's cron_deliver_env_var declaration lets the cron scheduler
    resolve seatalk targets without monkey-patching scheduler internals."""
    import cron.scheduler as scheduler

    monkeypatch.setattr(scheduler, "_KNOWN_DELIVERY_PLATFORMS", frozenset({"telegram"}))
    monkeypatch.setattr(scheduler, "_HOME_TARGET_ENV_VARS", {"telegram": "TELEGRAM_HOME_CHANNEL"})
    monkeypatch.setenv("SEATALK_HOME_CHANNEL", "group/Home")

    platform_registry.register(PlatformEntry(
        name="seatalk",
        label="SeaTalk",
        adapter_factory=lambda cfg: seatalk_adapter.SeaTalkAdapter(cfg),
        check_fn=lambda: True,
        cron_deliver_env_var="SEATALK_HOME_CHANNEL",
    ))

    assert scheduler._is_known_delivery_platform("seatalk") is True
    assert scheduler._resolve_single_delivery_target({}, "seatalk") == {
        "platform": "seatalk",
        "chat_id": "group/Home",
        "thread_id": None,
    }


def test_t08_06_patch_idempotent(monkeypatch):
    import tools.send_message_tool as send_message_tool

    original_parse = getattr(send_message_tool._parse_target_ref, "_seatalk_original", send_message_tool._parse_target_ref)
    original_send = getattr(send_message_tool._send_to_platform, "_seatalk_original", send_message_tool._send_to_platform)
    monkeypatch.setattr(send_message_tool, "_parse_target_ref", original_parse)
    monkeypatch.setattr(send_message_tool, "_send_to_platform", original_send)

    seatalk_adapter._patch_send_message_tool()
    seatalk_adapter._patch_send_to_platform()
    once = (
        send_message_tool._parse_target_ref,
        send_message_tool._send_to_platform,
    )
    seatalk_adapter._patch_send_message_tool()
    seatalk_adapter._patch_send_to_platform()

    assert once == (
        send_message_tool._parse_target_ref,
        send_message_tool._send_to_platform,
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
