from __future__ import annotations

import inspect
from pathlib import Path

from hermes_seatalk import adapter


ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text()
README_INLINE = " ".join(README.split())


def test_t09_01_readme_commands_are_copy_pasteable():
    assert "git clone https://github.com/arxeme/hermes-seatalk.git ~/.hermes/plugins/seatalk" in README
    assert "hermes plugins enable seatalk-platform" in README
    assert "hermes gateway setup" in README
    assert "hermes gateway restart" in README
    assert "PYTHONDONTWRITEBYTECODE=1 uv run --directory ../../hermes-agent pytest" in README


def test_t09_02_enable_restart_semantics_documented():
    assert "only records the plugin as enabled" in README
    assert "`register(ctx)` runs when a Hermes process starts" in README_INLINE
    assert "Restart the gateway after enabling the plugin or changing SeaTalk configuration" in README_INLINE


def test_t09_03_tui_requires_plugin_enable():
    assert "appear in `hermes setup` / `hermes gateway setup` only after" in README_INLINE
    assert "hermes plugins enable seatalk-platform" in README
    assert "does not clone, install, or enable the plugin" in README_INLINE


def test_t09_04_setup_wizard_order():
    source = inspect.getsource(adapter._seatalk_setup_wizard)
    assert source.index("SEATALK_APP_ID") < source.index("SEATALK_APP_SECRET")
    assert source.index("SEATALK_APP_SECRET") < source.index("SEATALK_SIGNING_SECRET")
    assert source.index("SEATALK_SIGNING_SECRET") < source.index("SeaTalk connection mode")
    assert source.index("SeaTalk connection mode") < source.index("SEATALK_RELAY_URL")
    assert source.index("SEATALK_RELAY_URL") < source.index("SEATALK_HOME_CHANNEL")


def test_t09_05_relay_mutual_exclusion():
    source = inspect.getsource(adapter._seatalk_setup_wizard)
    relay_block = source.split('if mode == "relay":', 1)[1].split("else:", 1)[0]
    assert "SEATALK_RELAY_URL" in relay_block
    assert "SEATALK_WEBHOOK_HOST" not in relay_block
    assert "SEATALK_WEBHOOK_PORT" not in relay_block
    assert "SEATALK_WEBHOOK_PATH" not in relay_block
    assert "webhook host, port, and path are ignored" in README_INLINE


def test_t09_06_webhook_mutual_exclusion():
    source = inspect.getsource(adapter._seatalk_setup_wizard)
    webhook_block = source.split("else:", 1)[1].split("for env_name, label in (", 1)[0]
    assert "SEATALK_WEBHOOK_HOST" in webhook_block
    assert "SEATALK_WEBHOOK_PORT" in webhook_block
    assert "SEATALK_WEBHOOK_PATH" in webhook_block
    assert "SEATALK_RELAY_URL" not in webhook_block
    assert "Webhook mode runs a local HTTP callback endpoint" in README
    assert "does not require\n`SEATALK_RELAY_URL`" in README


def test_t09_07_authorization_boundaries_are_documented():
    assert "SEATALK_ALLOWED_USERS` is the Hermes user authorization allowlist" in README
    assert "sender email is preferred as `user_id`" in README
    assert "employee code\nis preserved as the fallback identity" in README
    assert "SEATALK_GROUP_ALLOWED_USERS` is a\nSeaTalk channel pre-filter" in README
    assert "does not\nauthorize every user in that group" in README


def test_t09_08_troubleshooting_paths_are_documented():
    assert "hermes gateway status" in README
    assert "Static connected state means the required SeaTalk credentials" in README
    assert "Runtime health comes from the running adapter" in README
    assert "gateway logs" in README
    assert "restart the gateway process that loads\n  `~/.hermes/.env`" in README
