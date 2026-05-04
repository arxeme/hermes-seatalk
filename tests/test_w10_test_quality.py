from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("gateway", reason="requires Hermes gateway")

from gateway.platform_registry import PlatformEntry, platform_registry  # noqa: E402

from hermes_seatalk import adapter as seatalk_adapter  # noqa: E402

pytestmark = pytest.mark.requires_hermes


ROOT = Path(__file__).resolve().parents[1]


def test_t10_01_core_tests_do_not_require_real_seatalk_credentials():
    env_example = (ROOT / "env.example").read_text()
    assert "your_app_id" in env_example
    assert "your_app_secret" in env_example
    assert "your_signing_secret" in env_example
    assert "real" not in env_example.lower()
    assert "production" not in env_example.lower()


def test_t10_02a_env_isolation_can_set_seatalk_env():
    os.environ["SEATALK_W10_LEAK_CHECK"] = "leaked"
    assert os.environ["SEATALK_W10_LEAK_CHECK"] == "leaked"


def test_t10_02b_env_isolation_removed_prior_test_value():
    assert "SEATALK_W10_LEAK_CHECK" not in os.environ


def test_t10_03a_registry_isolation_can_register_platform():
    platform_registry.register(PlatformEntry(
        name="seatalk-w10-leak-check",
        label="SeaTalk W10",
        adapter_factory=lambda cfg: object(),
        check_fn=lambda: True,
    ))
    assert platform_registry.is_registered("seatalk-w10-leak-check")


def test_t10_03b_registry_isolation_removed_prior_test_entry():
    assert not platform_registry.is_registered("seatalk-w10-leak-check")


def test_t10_04a_patch_isolation_can_patch_runtime_modules():
    import tools.send_message_tool as send_message_tool
    from gateway.config import GatewayConfig

    seatalk_adapter._patch_send_message_tool()
    seatalk_adapter._patch_send_to_platform()
    seatalk_adapter._patch_home_channel()

    assert getattr(send_message_tool._parse_target_ref, "_seatalk_patched", False) is True
    assert getattr(send_message_tool._send_to_platform, "_seatalk_patched", False) is True
    assert getattr(GatewayConfig.get_home_channel, "_seatalk_patched", False) is True


def test_t10_04b_patch_isolation_removed_prior_test_wrappers():
    import tools.send_message_tool as send_message_tool
    from gateway.config import GatewayConfig

    assert not getattr(send_message_tool._parse_target_ref, "_seatalk_patched", False)
    assert not getattr(send_message_tool._send_to_platform, "_seatalk_patched", False)
    assert not getattr(GatewayConfig.get_home_channel, "_seatalk_patched", False)


def test_t10_05_repeatability_guards_are_autouse_fixtures():
    conftest = (ROOT / "tests" / "conftest.py").read_text()
    assert "def _isolate_env_vars" in conftest
    assert "def _isolate_platform_registry" in conftest
    assert "def _isolate_runtime_patches" in conftest
    assert "autouse=True" in conftest
