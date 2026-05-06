from __future__ import annotations

import sys
import types
from pathlib import Path

from hermes_seatalk import adapter


def _install_setup_module(monkeypatch, prompts, choices, saved):
    setup = types.ModuleType("hermes_cli.setup")
    setup.print_header = lambda _message: None
    setup.print_info = lambda _message: None
    setup.print_success = lambda _message: None
    setup.prompt = lambda _label, default="": prompts.pop(0) if prompts else default
    setup.prompt_choice = lambda _label, _options, default_index=0: choices.pop(0) if choices else default_index
    setup.save_config = lambda config: saved.append(config)

    package = types.ModuleType("hermes_cli")
    package.setup = setup
    monkeypatch.setitem(sys.modules, "hermes_cli", package)
    monkeypatch.setitem(sys.modules, "hermes_cli.setup", setup)
    return setup


def _run_wizard(monkeypatch, raw_config, prompts, choices):
    saved = []
    _install_setup_module(monkeypatch, prompts, choices, saved)
    monkeypatch.setattr(adapter, "_raw_config_file", lambda: raw_config)

    adapter._seatalk_setup_wizard()

    assert saved == [raw_config]
    return raw_config["platforms"]["seatalk"]["extra"]


def test_t2_08_01_wizard_add_account(monkeypatch):
    extra = _run_wizard(
        monkeypatch,
        {},
        prompts=[
            "default",
            "app-id",
            "app-secret",
            "signing-secret",
            "127.0.0.1",
            "8080",
            "/callback",
            "default",
            "group/Home",
            "ThreadHome",
            "alice@example.com,bob@example.com",
            "alice@example.com",
        ],
        choices=[0, 1, 0, 2, 0],
    )

    account = extra["accounts"]["default"]
    assert account["app_id"] == "app-id"
    assert account["app_secret"] == "app-secret"
    assert account["signing_secret"] == "signing-secret"
    assert account["mode"] == "webhook"
    assert account["dm_policy"] == "allowlist"
    assert account["allow_from"] == ["alice@example.com", "bob@example.com"]
    assert account["group_policy"] == "open"
    assert account["group_sender_allow_from"] == ["alice@example.com"]


def test_t2_08_02_wizard_edit_account_preserves_others(monkeypatch):
    raw_config = {
        "platforms": {
            "seatalk": {
                "enabled": True,
                "extra": {
                    "accounts": {
                        "default": {"enabled": True, "app_id": "keep"},
                        "staging": {"enabled": True, "app_id": "old"},
                    }
                },
            }
        }
    }
    extra = _run_wizard(
        monkeypatch,
        raw_config,
        prompts=[
            "staging",
            "new-app",
            "new-secret",
            "new-signing",
            "wss://relay.example.com/ws",
            "staging",
            "EmpHome",
            "",
            "alice@example.com",
        ],
        choices=[0, 0, 1, 0, 0],
    )

    assert extra["accounts"]["default"]["app_id"] == "keep"
    assert extra["accounts"]["staging"]["app_id"] == "new-app"
    assert extra["accounts"]["staging"]["mode"] == "relay"
    assert extra["accounts"]["staging"]["relay_url"] == "wss://relay.example.com/ws"


def test_t2_08_03_wizard_disable_and_remove(monkeypatch):
    raw_config = {
        "platforms": {
            "seatalk": {
                "enabled": True,
                "extra": {
                    "accounts": {
                        "default": {"enabled": True, "app_id": "app-default"},
                        "staging": {"enabled": True, "app_id": "app-staging"},
                    }
                },
            }
        }
    }

    extra = _run_wizard(monkeypatch, raw_config, ["staging"], [1])
    assert extra["accounts"]["staging"]["enabled"] is False

    extra = _run_wizard(monkeypatch, raw_config, ["staging"], [2])
    assert "staging" not in extra["accounts"]


def test_t2_08_04_wizard_home_channel(monkeypatch):
    extra = _run_wizard(
        monkeypatch,
        {},
        prompts=[
            "default",
            "app-id",
            "app-secret",
            "signing-secret",
            "127.0.0.1",
            "8080",
            "/callback",
            "default",
            "group/Home",
            "ThreadHome",
            "",
        ],
        choices=[0, 1, 1, 0, 0],
    )

    assert extra["home_channel_account_id"] == "default"
    assert extra["home_channel"] == "group/Home"
    assert extra["home_channel_thread_id"] == "ThreadHome"


def test_t2_08_05_wizard_does_not_write_env(monkeypatch):
    setup = _install_setup_module(monkeypatch, ["default"], [2], [])
    setup.save_env_value = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not write env"))
    monkeypatch.setattr(adapter, "_raw_config_file", lambda: {
        "platforms": {"seatalk": {"enabled": True, "extra": {"accounts": {}}}}
    })

    adapter._seatalk_setup_wizard()


def test_t2_08_06_wizard_has_no_pairing_choice():
    source = Path(adapter.__file__).read_text(encoding="utf-8")
    wizard_source = source[source.index("def _seatalk_setup_wizard") : source.index("def _cfg_csv")]

    assert '"pairing"' not in wizard_source
    assert "save_env_value" not in wizard_source
    assert "get_env_value" not in wizard_source


def test_t2_08_07_to_09_readme_accounts_and_group_format():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "accounts:" in readme
    assert "app_secret:" in readme
    assert "signing_secret:" in readme
    assert "config.yaml" in readme and "Protect this file" in readme
    assert "group_allow_from" in readme
    assert "raw SeaTalk `group_id`" in readme
    assert "home_channel" in readme and "group/<group_id>" in readme


def test_t2_08_10_publish_branch_content():
    script = Path("scripts/publish-release.sh").read_text(encoding="utf-8")

    assert "RELEASE_BRANCH=\"publish\"" in script
    assert "README.md" in script
    assert "hermes_seatalk" in script
    assert "no docs/, tests/, scripts/, deploy/" in script
    release_paths = script[script.index("RELEASE_PATHS=(") : script.index("RELEASE_BRANCH=")]
    assert "docs" not in release_paths
    assert "tests" not in release_paths
    assert "deploy" not in release_paths


def test_t2_08_11_deploy_does_not_overwrite_config_yaml_by_default():
    script = Path("deploy/deploy-seatalk-plugin.sh").read_text(encoding="utf-8")

    assert "config.yaml" not in script
    assert "RUNTIME_ENV_FILE" in script
