from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from hermes_seatalk import adapter
from hermes_seatalk.targets import SeaTalkTarget, parse_seatalk_target


class FakeSeaTalkClient:
    def __init__(self, name: str):
        self.name = name
        self.calls = []
        self.email_map = {}

    async def send_single_chat(self, employee_code, message, thread_id=None):
        self.calls.append(("single", employee_code, message, thread_id))
        return {"code": 0, "message_id": f"{self.name}-{len(self.calls)}"}

    async def send_group_chat(self, group_id, message, thread_id=None):
        self.calls.append(("group", group_id, message, thread_id))
        return {"code": 0, "message_id": f"{self.name}-{len(self.calls)}"}

    async def send_single_chat_typing(self, employee_code, thread_id=None):
        self.calls.append(("typing-single", employee_code, None, thread_id))

    async def send_group_chat_typing(self, group_id, thread_id=None):
        self.calls.append(("typing-group", group_id, None, thread_id))

    async def get_employee_code_by_email(self, emails):
        return {email: self.email_map.get(email) for email in emails}

    async def get_group_info(self, group_id):
        self.calls.append(("group-info", group_id, None, None))
        return {"group_name": f"{self.name}-{group_id}"}

    async def download_media(self, _url):
        self.calls.append(("download", _url, None, None))
        return b"image-bytes", "image/png"

    async def close(self):
        return None


def _account(app_id: str, **overrides):
    account = {
        "enabled": True,
        "app_id": app_id,
        "app_secret": f"{app_id}-secret",
        "signing_secret": f"{app_id}-signing",
        "mode": "webhook",
        "webhook_host": "127.0.0.1",
        "webhook_port": 8080,
        "webhook_path": "/callback",
    }
    account.update(overrides)
    return account


def _config(clients: dict[str, FakeSeaTalkClient], **extra):
    base = {
        "accounts": {
            "default": _account("app-default"),
            "staging": _account("app-staging"),
        },
        "clients": clients,
        "outbound_coalescing": False,
    }
    base.update(extra)
    return SimpleNamespace(enabled=True, extra=base)


def test_t2_07_01_to_05_and_15_parser_account_prefix():
    known = {"default", "staging"}

    assert parse_seatalk_target("EmpABC", known_accounts=known) == SeaTalkTarget(
        chat_id="EmpABC",
        thread_id=None,
        is_group=False,
        is_email=False,
    )
    target = parse_seatalk_target("staging:EmpABC", known_accounts=known)
    assert target == SeaTalkTarget(
        chat_id="EmpABC",
        thread_id=None,
        is_group=False,
        is_email=False,
        account_id="staging",
    )
    assert parse_seatalk_target("group/GroupABC", known_accounts=known).is_group is True
    target = parse_seatalk_target("staging:group/GroupABC:ThreadXYZ", known_accounts=known)
    assert target == SeaTalkTarget(
        chat_id="group/GroupABC",
        thread_id="ThreadXYZ",
        is_group=True,
        is_email=False,
        account_id="staging",
    )
    assert parse_seatalk_target("seatalk:staging:EmpABC", known_accounts=known).account_id == "staging"


def test_t2_07_14_seatalk_target_account_id_default():
    target = SeaTalkTarget(chat_id="EmpABC", thread_id=None, is_group=False, is_email=False)

    assert target.account_id is None


@pytest.mark.asyncio
async def test_t2_07_06_metadata_account_precedence():
    default = FakeSeaTalkClient("default")
    staging = FakeSeaTalkClient("staging")
    seatalk = adapter.SeaTalkAdapter(_config({"default": default, "staging": staging}))

    await seatalk.send("staging:EmpABC", "hello", metadata={"seatalk_account_id": "default"})

    assert default.calls[0][0:2] == ("single", "EmpABC")
    assert staging.calls == []


@pytest.mark.asyncio
async def test_t2_07_07_default_fallback():
    default = FakeSeaTalkClient("default")
    staging = FakeSeaTalkClient("staging")
    seatalk = adapter.SeaTalkAdapter(_config({"default": default, "staging": staging}))

    await seatalk.send("EmpABC", "hello")

    assert default.calls[0][0:2] == ("single", "EmpABC")
    assert staging.calls == []


@pytest.mark.asyncio
async def test_t2_07_08_first_enabled_fallback():
    alpha = FakeSeaTalkClient("alpha")
    staging = FakeSeaTalkClient("staging")
    cfg = _config(
        {"alpha": alpha, "staging": staging},
        accounts={
            "staging": _account("app-staging"),
            "alpha": _account("app-alpha"),
        },
    )
    seatalk = adapter.SeaTalkAdapter(cfg)

    await seatalk.send("EmpABC", "hello")

    assert alpha.calls[0][0:2] == ("single", "EmpABC")
    assert staging.calls == []


@pytest.mark.asyncio
async def test_t2_07_09_send_typing_and_media_use_target_runtime(tmp_path: Path):
    default = FakeSeaTalkClient("default")
    staging = FakeSeaTalkClient("staging")
    seatalk = adapter.SeaTalkAdapter(_config({"default": default, "staging": staging}))
    image = tmp_path / "photo.png"
    image.write_bytes(b"image-bytes")
    document = tmp_path / "report.bin"
    document.write_bytes(b"file-bytes")

    await seatalk.send("staging:EmpABC", "text")
    await seatalk.send_typing("staging:EmpABC")
    # SeaTalk-hosted URL exercises the authenticated client.download_media path
    # (Fix-8 ([adapter.py:_fetch_outbound_media_bytes]) routes non-SeaTalk URLs
    # through unauthenticated aiohttp instead).
    await seatalk.send_image("staging:EmpABC", "https://openapi.seatalk.io/media/photo.png")
    await seatalk.send_image_file("staging:EmpABC", str(image))
    await seatalk.send_document("staging:group/GroupABC", str(document))

    assert default.calls == []
    assert [call[0] for call in staging.calls] == [
        "single",
        "typing-single",
        "download",
        "single",
        "single",
        "group",
    ]


@pytest.mark.asyncio
async def test_t2_07_10_home_channel_env_account_target(monkeypatch):
    monkeypatch.setenv("SEATALK_HOME_CHANNEL", "staging:group/Home")
    default = FakeSeaTalkClient("default")
    staging = FakeSeaTalkClient("staging")
    seatalk = adapter.SeaTalkAdapter(_config(
        {"default": default, "staging": staging},
    ))

    await seatalk.send("seatalk", "hello")

    assert default.calls == []
    assert staging.calls[0][0:2] == ("group", "Home")


def test_t2_07_11_cron_account_target(monkeypatch):
    """Account-qualified home channels resolve via the declarative
    cron_deliver_env_var path (no scheduler monkey-patching needed)."""
    scheduler = pytest.importorskip("cron.scheduler")
    from gateway.platform_registry import PlatformEntry, platform_registry

    monkeypatch.setattr(scheduler, "_KNOWN_DELIVERY_PLATFORMS", frozenset({"telegram"}))
    monkeypatch.setattr(scheduler, "_HOME_TARGET_ENV_VARS", {"telegram": "TELEGRAM_HOME_CHANNEL"})
    monkeypatch.setenv("SEATALK_HOME_CHANNEL", "staging:group/Home")

    platform_registry.register(PlatformEntry(
        name="seatalk",
        label="SeaTalk",
        adapter_factory=lambda cfg: adapter.SeaTalkAdapter(cfg),
        check_fn=lambda: True,
        cron_deliver_env_var="SEATALK_HOME_CHANNEL",
    ))

    assert scheduler._resolve_single_delivery_target({}, "seatalk") == {
        "platform": "seatalk",
        "chat_id": "staging:group/Home",
        "thread_id": None,
    }


def test_t2_07_12_and_15_send_message_parser(monkeypatch):
    send_message_tool = pytest.importorskip("tools.send_message_tool")

    original = getattr(send_message_tool._parse_target_ref, "_seatalk_original", send_message_tool._parse_target_ref)
    monkeypatch.setattr(send_message_tool, "_parse_target_ref", original)
    monkeypatch.setattr(
        adapter,
        "_config_file_extra",
        lambda: {"accounts": {"default": {}, "staging": {}}},
    )
    adapter._patch_send_message_tool()

    assert send_message_tool._parse_target_ref("seatalk", "seatalk:staging:EmpABC") == (
        "staging:EmpABC",
        None,
        True,
    )
    assert send_message_tool._parse_target_ref("discord", "123456789:987654321") == (
        "123456789",
        "987654321",
        True,
    )


@pytest.mark.asyncio
async def test_t2_07_13_get_chat_info_account_target():
    default = FakeSeaTalkClient("default")
    staging = FakeSeaTalkClient("staging")
    seatalk = adapter.SeaTalkAdapter(_config({"default": default, "staging": staging}))

    dm_info = await seatalk.get_chat_info("staging:EmpABC")
    info = await seatalk.get_chat_info("staging:group/GroupABC")

    assert dm_info == {"name": "EmpABC", "type": "dm", "chat_id": "staging:EmpABC"}
    assert info["name"] == "staging-GroupABC"
    assert info["chat_id"] == "staging:group/GroupABC"
    assert default.calls == []
    assert staging.calls == [("group-info", "GroupABC", None, None)]
