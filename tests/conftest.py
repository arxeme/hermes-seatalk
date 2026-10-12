from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _isolate_env_vars():
    tracked = {
        key: value
        for key, value in os.environ.items()
        if key.startswith("SEATALK_")
        or key.startswith("GATEWAY_")
        or key.startswith("HERMES_SEATALK_")
        or key in {"HERMES_HOME", "HOME_CHANNEL"}
    }
    yield
    for key in list(os.environ):
        if (
            key.startswith("SEATALK_")
            or key.startswith("GATEWAY_")
            or key.startswith("HERMES_SEATALK_")
            or key in {"HERMES_HOME", "HOME_CHANNEL"}
        ) and key not in tracked:
            os.environ.pop(key, None)
    for key, value in tracked.items():
        os.environ[key] = value


@pytest.fixture(autouse=True)
def _isolate_platform_registry():
    try:
        from gateway.platform_registry import platform_registry
    except Exception:
        yield
        return

    entries = dict(getattr(platform_registry, "_entries", {}))
    yield
    platform_registry._entries.clear()
    platform_registry._entries.update(entries)


@pytest.fixture(autouse=True)
def _isolate_runtime_patches():
    snapshots = []

    try:
        import tools.send_message_tool as send_message_tool

        snapshots.append((send_message_tool, "_send_to_platform", send_message_tool._send_to_platform))
    except Exception:
        pass

    yield

    for obj, name, value in snapshots:
        setattr(obj, name, value)


@pytest.fixture
def seatalk_platform(monkeypatch, tmp_path):
    gateway_config = pytest.importorskip("gateway.config")
    from gateway.platform_registry import PlatformEntry, platform_registry
    from hermes_seatalk import adapter

    captured = {}
    adapter.register(SimpleNamespace(
        register_platform=lambda **kwargs: captured.update(kwargs),
        register_tool=lambda **kwargs: None,
    ))
    platform_registry.register(PlatformEntry(**captured))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    return gateway_config.Platform("seatalk")
