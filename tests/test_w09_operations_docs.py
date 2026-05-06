from __future__ import annotations

import inspect
from pathlib import Path

from hermes_seatalk import adapter


ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text()
README_INLINE = " ".join(README.split())


def test_t09_01_readme_commands_are_copy_pasteable():
    assert "hermes plugins install arxeme/hermes-seatalk --enable && hermes gateway restart" in README
    assert "hermes gateway setup" in README
    assert "hermes gateway restart" in README
    assert "PYTHONDONTWRITEBYTECODE=1 uv run --directory ../../hermes-agent pytest" in README


def test_t09_02_enable_restart_semantics_documented():
    assert "clones the plugin into the user plugin directory" in README_INLINE
    assert "records `seatalk-platform` as enabled" in README
    assert "`register(ctx)` runs when a Hermes process starts" in README_INLINE
    assert "Restart the gateway after changing SeaTalk configuration" in README_INLINE


def test_t09_03_tui_requires_plugin_enable():
    assert "appear in `hermes setup` / `hermes gateway setup` only after" in README_INLINE
    assert "hermes plugins install arxeme/hermes-seatalk --enable" in README
    assert "does not clone, install, enable the plugin" in README_INLINE


def test_t09_04_setup_wizard_order():
    source = inspect.getsource(adapter._seatalk_setup_wizard)
    assert source.index("SeaTalk account id") < source.index("SeaTalk account action")
    assert source.index("SeaTalk account action") < source.index("SeaTalk app id")
    assert source.index("SeaTalk app id") < source.index("SeaTalk app secret")
    assert source.index("SeaTalk app secret") < source.index("SeaTalk signing secret")
    assert source.index("SeaTalk signing secret") < source.index("SeaTalk connection mode")
    assert source.index("SeaTalk connection mode") < source.index("relay_url")
    assert source.index("relay_url") < source.index("DM policy")
    assert source.index("DM policy") < source.index("Group policy")
    assert source.index("Group policy") < source.index("SeaTalk home channel target")
    assert "save_env_value" in source
    assert "get_env_value" in source
    assert '"pairing"' not in source
    assert "SEATALK_ALLOW_ALL_USERS" not in source
    assert "GATEWAY_ALLOW_ALL_USERS" not in source
    assert "allow_all" not in source


def test_t09_05_relay_mutual_exclusion():
    source = inspect.getsource(adapter._seatalk_setup_wizard)
    relay_block = source.split('if mode == "relay":', 1)[1].split("else:", 1)[0]
    assert "relay_url" in relay_block
    assert "webhook_host" in relay_block
    assert "webhook_port" in relay_block
    assert "webhook_path" in relay_block
    assert "Relay mode uses a WebSocket relay service" in README_INLINE


def test_t09_06_webhook_mutual_exclusion():
    source = inspect.getsource(adapter._seatalk_setup_wizard)
    webhook_block = source.split('if mode == "relay":', 1)[1].split("else:", 1)[1].split("for key, label in (", 1)[0]
    assert "webhook_host" in webhook_block
    assert "webhook_port" in webhook_block
    assert "webhook_path" in webhook_block
    assert "relay_url" in webhook_block
    assert "Webhook mode runs a local HTTP callback endpoint" in README_INLINE
    assert "replaces `relay_url` with" in README


def test_t09_07_authorization_boundaries_are_documented():
    assert "`dm_policy` controls direct messages" in README
    assert "`allow_from`" in README
    assert "sender email is preferred as `user_id`" in README_INLINE
    assert "employee code is preserved as the fallback identity" in README_INLINE
    assert "`group_policy` controls group chats" in README
    assert "do not prefix values with `group/`" in README
    assert "`group_sender_allow_from` can restrict" in README
    assert "every sender in the allowed groups can trigger Hermes" in README_INLINE


def test_t09_08_troubleshooting_paths_are_documented():
    assert "hermes gateway status" in README
    assert "Static connected state means the required SeaTalk credentials" in README
    assert "Runtime health comes from the running adapter" in README
    assert "gateway logs" in README
    assert "`~/.hermes/config.yaml`" in README
    assert "Protect this file as a secret-bearing configuration" in README
