#!/usr/bin/env bash
# One-line installer for the hermes-agent vision runtime-credentials hotfix.
#
# Does NOT restart the gateway by default (so it can run mid-flow during a
# fresh install / upgrade pipeline). Pass --restart to restart afterwards,
# or restart yourself when the whole flow is done:
#   systemctl --user restart hermes-gateway
#
# Remote (note: the patch lives on the `main` branch, NOT the default `publish`):
#   curl -fsSL https://raw.githubusercontent.com/arxeme/hermes-seatalk/main/deploy/patches/hotfix-vision-runtime-credentials/install.sh \
#     | bash -s -- --hermes-root ~/.hermes/hermes-agent
#
# Local (from a repo checkout):
#   ./install.sh --hermes-root ~/.hermes/hermes-agent
#
# Upstream tracking: NousResearch/hermes-agent#43251 / PR #43254.
# Remove once the target runs a hermes-agent release containing that PR.
set -euo pipefail

SCRIPT_SOURCE="${BASH_SOURCE[0]:-}"
if [[ -n "$SCRIPT_SOURCE" && -f "$SCRIPT_SOURCE" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"
else
    SCRIPT_DIR="$(pwd)"
fi

HERMES_ROOT="${HERMES_ROOT:-${HOME}/.hermes/hermes-agent}"
PYTHON_BIN=""
PATCH_REPO="${HERMES_SEATALK_PATCH_REPO:-arxeme/hermes-seatalk}"
PATCH_REF="${HERMES_SEATALK_PATCH_REF:-main}"
PATCH_DIR_IN_REPO="deploy/patches/hotfix-vision-runtime-credentials"
BACKUP_SUFFIX=".bak.hotfix-vision-runtime-credentials"
RESTORE=0
RESTART=0
APPLY_TMP=""

cleanup() {
    if [[ -n "$APPLY_TMP" ]]; then
        rm -f "$APPLY_TMP"
    fi
}
trap cleanup EXIT

usage() {
    cat <<'EOF'
Usage: install.sh [options]

Options:
  --hermes-root PATH   hermes-agent install root containing agent/auxiliary_client.py
                       (default: ~/.hermes/hermes-agent)
  --python PATH        Python interpreter to run the patcher
                       (default: <hermes-root>/venv/bin/python, fallback python3)
  --restore            Restore agent/auxiliary_client.py from the hotfix backup
  --restart            Restart the hermes-gateway systemd user service afterwards
                       (default: no restart, so this can run mid-flow during
                       install/upgrade pipelines)
  --no-restart         Accepted for compatibility (no-op; no restart is the default)
  --repo OWNER/REPO    Patch repo for remote self-install (default: arxeme/hermes-seatalk)
  --ref REF            Patch repo ref (default: main — the patch is NOT on `publish`)
  -h, --help           Show this help
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --hermes-root)
            [[ $# -ge 2 ]] || { echo "--hermes-root requires a path" >&2; exit 1; }
            HERMES_ROOT="$2"
            shift 2
            ;;
        --python)
            [[ $# -ge 2 ]] || { echo "--python requires a path" >&2; exit 1; }
            PYTHON_BIN="$2"
            shift 2
            ;;
        --restore)
            RESTORE=1
            shift
            ;;
        --restart)
            RESTART=1
            shift
            ;;
        --no-restart)
            # Compatibility no-op: not restarting is already the default.
            shift
            ;;
        --repo)
            [[ $# -ge 2 ]] || { echo "--repo requires OWNER/REPO" >&2; exit 1; }
            PATCH_REPO="$2"
            shift 2
            ;;
        --ref)
            [[ $# -ge 2 ]] || { echo "--ref requires a ref" >&2; exit 1; }
            PATCH_REF="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

TARGET="${HERMES_ROOT}/agent/auxiliary_client.py"
if [[ ! -f "$TARGET" ]]; then
    echo "Target not found: $TARGET" >&2
    echo "Pass --hermes-root pointing at a hermes-agent install/checkout." >&2
    exit 1
fi

if [[ -z "$PYTHON_BIN" ]]; then
    if [[ -x "${HERMES_ROOT}/venv/bin/python" ]]; then
        PYTHON_BIN="${HERMES_ROOT}/venv/bin/python"
    else
        PYTHON_BIN="python3"
    fi
fi

restart_gateway() {
    if [[ "$RESTART" -ne 1 ]]; then
        echo "Gateway NOT restarted (default). Restart it when your flow is done:"
        echo "  systemctl --user restart hermes-gateway"
        return
    fi
    if command -v systemctl >/dev/null 2>&1 \
            && systemctl --user list-unit-files hermes-gateway.service >/dev/null 2>&1; then
        systemctl --user restart hermes-gateway
        echo "hermes-gateway restarted."
    else
        echo "hermes-gateway service not found via systemctl --user; restart your gateway manually."
    fi
}

if [[ "$RESTORE" -eq 1 ]]; then
    BACKUP="${TARGET}${BACKUP_SUFFIX}"
    if [[ ! -f "$BACKUP" ]]; then
        echo "Backup not found: $BACKUP" >&2
        exit 1
    fi
    cp "$BACKUP" "$TARGET"
    echo "RESTORED from $BACKUP"
    restart_gateway
    exit 0
fi

resolve_apply_py() {
    local local_apply="${SCRIPT_DIR}/apply.py"
    if [[ -f "$local_apply" ]]; then
        APPLY_PATH="$local_apply"
        return
    fi
    if ! command -v curl >/dev/null 2>&1; then
        echo "apply.py not found locally and curl is unavailable." >&2
        echo "Run from a repo checkout, or install curl for remote one-line installation." >&2
        exit 1
    fi
    local raw_url="https://raw.githubusercontent.com/${PATCH_REPO}/${PATCH_REF}/${PATCH_DIR_IN_REPO}/apply.py"
    APPLY_TMP="$(mktemp "${TMPDIR:-/tmp}/hotfix-vision-apply.XXXXXX.py")"
    if ! curl -fsSL "$raw_url" -o "$APPLY_TMP"; then
        echo "Failed to download $raw_url" >&2
        exit 1
    fi
    chmod 0700 "$APPLY_TMP"
    APPLY_PATH="$APPLY_TMP"
}

APPLY_PATH=""
resolve_apply_py

"$PYTHON_BIN" "$APPLY_PATH" "$TARGET"

"$PYTHON_BIN" -m py_compile "$TARGET"
echo "Syntax check passed: $TARGET"

restart_gateway
