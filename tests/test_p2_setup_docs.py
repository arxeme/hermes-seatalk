from __future__ import annotations

import sys
import types
from pathlib import Path

from hermes_seatalk import adapter


def _install_setup_module(monkeypatch, prompts, choices, saved, saved_env=None, env_values=None):
    setup = types.ModuleType("hermes_cli.setup")
    setup.print_header = lambda _message: None
    setup.print_info = lambda _message: None
    setup.print_success = lambda _message: None
    setup.prompt = lambda _label, default="": prompts.pop(0) if prompts else default
    setup.prompt_choice = lambda _label, _options, default_index=0: choices.pop(0) if choices else default_index
    setup.save_config = lambda config: saved.append(config)

    saved_env = saved_env if saved_env is not None else []
    env_values = env_values if env_values is not None else {}
    config = types.ModuleType("hermes_cli.config")
    config.get_env_value = lambda key: env_values.get(key)
    config.save_env_value = lambda key, value: saved_env.append((key, value))

    package = types.ModuleType("hermes_cli")
    package.setup = setup
    package.config = config
    monkeypatch.setitem(sys.modules, "hermes_cli", package)
    monkeypatch.setitem(sys.modules, "hermes_cli.setup", setup)
    monkeypatch.setitem(sys.modules, "hermes_cli.config", config)
    return setup


def _run_wizard(monkeypatch, raw_config, prompts, choices, saved_env=None, env_values=None):
    saved = []
    _install_setup_module(monkeypatch, prompts, choices, saved, saved_env=saved_env, env_values=env_values)
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
            "alice@example.com,bob@example.com",
            "alice@example.com",
            "default:group/Home",
            "",
            "SeaTalk Home",
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
            "alice@example.com",
            "staging:alice@example.com",
            "ThreadHome",
            "Staging Home",
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


def test_t2_08_04_wizard_does_not_write_home_channel_config(monkeypatch):
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
            "",
            "",
            "",
            "SeaTalk Home",
        ],
        choices=[0, 1, 1, 0, 0],
    )

    assert "home_channel_account_id" not in extra
    assert "home_channel" not in extra
    assert "home_channel_thread_id" not in extra


def test_t2_08_05_wizard_writes_home_channel_env_not_secrets(monkeypatch):
    saved_env = []
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
            "",
            "default:group/Home",
            "ThreadHome",
            "SeaTalk Ops",
        ],
        choices=[0, 1, 1, 0, 0],
        saved_env=saved_env,
    )

    assert "home_channel" not in extra
    assert saved_env == [
        ("SEATALK_HOME_CHANNEL", "default:group/Home"),
        ("SEATALK_HOME_CHANNEL_THREAD_ID", "ThreadHome"),
        ("SEATALK_HOME_CHANNEL_NAME", "SeaTalk Ops"),
    ]
    assert adapter.os.environ["SEATALK_HOME_CHANNEL"] == "default:group/Home"
    assert adapter.os.environ["SEATALK_HOME_CHANNEL_THREAD_ID"] == "ThreadHome"
    assert adapter.os.environ["SEATALK_HOME_CHANNEL_NAME"] == "SeaTalk Ops"
    assert "SEATALK_APP_SECRET" not in {key for key, _value in saved_env}
    assert "SEATALK_SIGNING_SECRET" not in {key for key, _value in saved_env}


def test_t2_08_05b_wizard_disable_remove_does_not_write_env(monkeypatch):
    saved_env = []
    _install_setup_module(monkeypatch, ["default"], [2], [], saved_env=saved_env)
    monkeypatch.setattr(adapter, "_raw_config_file", lambda: {
        "platforms": {"seatalk": {"enabled": True, "extra": {"accounts": {}}}}
    })

    adapter._seatalk_setup_wizard()

    assert saved_env == []


def test_t2_08_06_wizard_has_no_pairing_choice():
    source = Path(adapter.__file__).read_text(encoding="utf-8")
    wizard_source = source[source.index("def _seatalk_setup_wizard") : source.index("def _cfg_csv")]

    assert '"pairing"' not in wizard_source
    assert "save_env_value" in wizard_source
    assert "get_env_value" in wizard_source


def test_t2_08_07_to_09_readme_accounts_and_group_format():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "accounts:" in readme
    assert "app_secret:" in readme
    assert "signing_secret:" in readme
    assert "config.yaml" in readme and "Protect this file" in readme
    assert "group_allow_from" in readme
    assert "raw SeaTalk `group_id`" in readme
    assert "SEATALK_HOME_CHANNEL" in readme
    assert "staging:group/123" in readme


def test_t2_08_10_publish_branch_content():
    script = Path("scripts/publish-release.sh").read_text(encoding="utf-8")

    assert "RELEASE_BRANCH=\"publish\"" in script
    assert "README.md" in script
    assert "hermes_seatalk" in script
    assert "pyproject.toml" in script
    assert "--tag <version-tag>" in script
    assert "--message <commit-message>" in script
    assert "COMMIT_MESSAGE" in script
    assert "git -C \"$TMP_WORKTREE\" commit -q -m \"$COMMIT_MSG\"" in script
    assert "no docs/, tests/, scripts/, deploy/" in script
    release_paths = script[script.index("RELEASE_PATHS=(") : script.index("RELEASE_BRANCH=")]
    assert "docs" not in release_paths
    assert "tests" not in release_paths
    assert "deploy" not in release_paths


def test_t2_08_11_deploy_does_not_overwrite_config_yaml_by_default():
    script = Path("deploy/deploy-seatalk-plugin.sh").read_text(encoding="utf-8")

    assert "config.yaml" not in script
    assert "RUNTIME_ENV_FILE" in script
