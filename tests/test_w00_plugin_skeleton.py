from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _manifest_text() -> str:
    return (ROOT / "plugin.yaml").read_text()


def test_t00_01_manifest_can_be_parsed():
    text = _manifest_text()

    assert "name: seatalk-platform" in text
    assert "kind: platform" in text
    assert "version:" in text
    assert "requires_env:" in text
    for name in (
        "SEATALK_APP_SECRET",
        "SEATALK_SIGNING_SECRET",
    ):
        assert f"  - {name}" in text


def test_t00_02_import_has_no_registration_side_effect():
    import adapter

    assert callable(adapter.register)
    assert adapter.SEATALK_PLATFORM == "seatalk"
    assert adapter.SEATALK_PLUGIN_NAME == "seatalk-platform"


def test_t00_03_register_can_be_imported():
    from adapter import register
    from hermes_seatalk.adapter import register as package_register

    assert callable(register)
    assert register is package_register


def test_t00_04_loader_style_package_import():
    module_name = "hermes_plugins.seatalk_test"
    spec = importlib.util.spec_from_file_location(
        module_name,
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    module.__package__ = module_name
    module.__path__ = [str(ROOT)]
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        assert callable(module.register)
    finally:
        sys.modules.pop(module_name, None)


def test_t00_05_env_example_is_complete_and_placeholder_only():
    text = (ROOT / "env.example").read_text()

    for name in (
        "SEATALK_APP_SECRET",
        "SEATALK_SIGNING_SECRET",
    ):
        assert name in text

    assert "your_app_secret" in text
    assert "your_signing_secret" in text
    assert "platforms:" in text
    assert "app_id: your_app_id" in text
    assert "relay_url: wss://relay.example.com/ws" in text
