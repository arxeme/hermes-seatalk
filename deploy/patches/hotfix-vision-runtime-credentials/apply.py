#!/usr/bin/env python3
"""Hotfix: bridge _RUNTIME_MAIN_* credentials into vision auto-detect.

Root cause: agent.turn_context calls set_runtime_main(agent.provider, ...)
where agent.provider is the flattened "custom" (not "custom:<name>") for
named custom providers. resolve_vision_provider_client's auto branch then
calls resolve_provider_client("custom", ...) WITHOUT explicit_base_url /
explicit_api_key, hitting "custom/main requested but no endpoint
credentials found" even though _RUNTIME_MAIN_BASE_URL / _RUNTIME_MAIN_API_KEY
are populated. Every vision_analyze call then fails with
"No LLM provider configured for task=vision provider=auto".

The fix mirrors the _resolve_auto() bridge added by upstream PR #35259.

Upstream tracking: issue NousResearch/hermes-agent#43251,
PR NousResearch/hermes-agent#43254. Remove this hotfix once the VM runs a
hermes-agent release containing that PR.

Usage (run as the hermes user on the VM):
    <venv-python> apply.py [path-to-auxiliary_client.py]
    # default target: ~/.hermes/hermes-agent/agent/auxiliary_client.py

Idempotent: re-running on an already-patched file is a no-op.
A one-time backup is written next to the target with suffix
".bak.hotfix-vision-runtime-credentials" (also the rollback source).
"""
import shutil
import sys
from pathlib import Path

DEFAULT_TARGET = Path.home() / ".hermes/hermes-agent/agent/auxiliary_client.py"
BACKUP_SUFFIX = ".bak.hotfix-vision-runtime-credentials"

OLD_BLOCK = '''            else:
                rpc_client, rpc_model = resolve_provider_client(
                    main_provider, vision_model,
                    api_mode=resolved_api_mode,
                    is_vision=True)'''

NEW_BLOCK = '''            else:
                # HOTFIX: bridge _RUNTIME_MAIN_* into resolve_provider_client
                # so a "custom:<name>" main provider that the agent resolver
                # flattened to bare "custom" still routes through the configured
                # endpoint. Mirrors _resolve_auto (#35259) for the vision path.
                # Upstream: hermes-agent#43251 / PR #43254.
                rpc_client, rpc_model = resolve_provider_client(
                    main_provider, vision_model,
                    explicit_base_url=_RUNTIME_MAIN_BASE_URL or None,
                    explicit_api_key=_RUNTIME_MAIN_API_KEY or None,
                    api_mode=resolved_api_mode or (_RUNTIME_MAIN_API_MODE or None),
                    is_vision=True)'''


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TARGET
    if not target.is_file():
        print(f"TARGET_NOT_FOUND: {target}")
        return 2
    backup = target.with_name(target.name + BACKUP_SUFFIX)

    src = target.read_text()
    # Detect by the functional line, not the full block: an earlier deployed
    # variant of this hotfix (or the merged upstream fix) may carry different
    # comment text but the same bridge.
    if "explicit_base_url=_RUNTIME_MAIN_BASE_URL or None," in src:
        print("ALREADY_PATCHED")
        return 0
    occurrences = src.count(OLD_BLOCK)
    if occurrences == 0:
        print("OLD_BLOCK_NOT_FOUND — hermes-agent version differs; "
              "check whether upstream PR #43254 is already included")
        return 2
    if occurrences > 1:
        print(f"OLD_BLOCK_AMBIGUOUS — found {occurrences} matches; aborting")
        return 2

    if not backup.exists():
        shutil.copy2(target, backup)
        print(f"BACKUP_CREATED: {backup}")
    else:
        print(f"BACKUP_EXISTS_KEEP: {backup}")

    target.write_text(src.replace(OLD_BLOCK, NEW_BLOCK))
    print("PATCHED_OK — restart the gateway: systemctl --user restart hermes-gateway")
    return 0


if __name__ == "__main__":
    sys.exit(main())
