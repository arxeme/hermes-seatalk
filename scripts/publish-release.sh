#!/usr/bin/env bash
# Publish minimum runtime plugin files from main to the publish branch.
# Requires Git >= 2.15 (git worktree add --orphan).
#
# Release flow: annotate a release-candidate tag on main with the release notes
# and push it. CI runs this script with --rc-tag, so the tag message becomes the
# publish commit message and the version tag (the rc tag without its suffix)
# lands on the published commit.
#
# Usage:
#   ./scripts/publish-release.sh --rc-tag <vYYYY.M.D-rc>
#   ./scripts/publish-release.sh [--tag <version-tag>] [--message <commit-message>]
#
# Examples:
#   ./scripts/publish-release.sh --rc-tag v2026.9.14-rc
#   ./scripts/publish-release.sh --tag v2026.9.14 --message "publish: release v2026.9.14 runtime plugin"
#
# Backward compatibility:
#   ./scripts/publish-release.sh v1.0.0
set -euo pipefail

# Paths included in the publish branch. Runtime only: no docs/, tests/,
# scripts/, deploy/, or local config. The bundled Python SeaTalk OAPI SDK is
# required at runtime by websocket mode (imported via the fallback path in
# hermes_seatalk/websocket.py), so its package ships in the runtime tree too.
# The reference Go SDK and the developer guides under ref/ are not shipped.
RELEASE_PATHS=(
    plugin.yaml
    __init__.py
    adapter.py
    hermes_seatalk
    ref/seatalk-oapi/seatalk-oapi-sdk-py/seatalk_oapi_sdk
    pyproject.toml
    requirements.txt
    env.example
    README.md
)

# Development-only top-level entries. Every top-level entry in the source tree
# must be named by one of the two lists (a RELEASE_PATHS entry classifies its
# top-level component): a new runtime file left out of RELEASE_PATHS would
# otherwise ship a plugin that is missing it, with nothing but a skipped line.
DEV_PATHS=(
    .github
    .gitignore
    deploy
    docs
    scripts
    tests
)

RELEASE_BRANCH="publish"
SOURCE_REF="main"
MAIN_REF="main"
RC_SUFFIX="-rc"
RC_TAG=""
VERSION=""
COMMIT_MESSAGE=""

usage() {
    sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'
}

require_value() {
    local option="$1"
    local value="${2:-}"
    if [[ -z "$value" ]]; then
        echo "Error: $option requires a value." >&2
        exit 1
    fi
}

while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --rc-tag)
            require_value "$1" "${2:-}"
            RC_TAG="$2"; shift 2 ;;
        --rc-tag=*)
            RC_TAG="${1#--rc-tag=}"; require_value "--rc-tag" "$RC_TAG"; shift ;;
        --tag)
            require_value "$1" "${2:-}"
            [[ -n "$VERSION" ]] && { echo "Error: tag specified more than once." >&2; exit 1; }
            VERSION="$2"; shift 2 ;;
        --tag=*)
            [[ -n "$VERSION" ]] && { echo "Error: tag specified more than once." >&2; exit 1; }
            VERSION="${1#--tag=}"; require_value "--tag" "$VERSION"; shift ;;
        --message|-m)
            require_value "$1" "${2:-}"; COMMIT_MESSAGE="$2"; shift 2 ;;
        --message=*|-m=*)
            COMMIT_MESSAGE="${1#*=}"; require_value "--message" "$COMMIT_MESSAGE"; shift ;;
        --help|-h)
            usage; exit 0 ;;
        --*)
            echo "Error: unknown option: $1" >&2; usage >&2; exit 1 ;;
        *)
            [[ -n "$VERSION" ]] && { echo "Error: unexpected positional argument: $1" >&2; usage >&2; exit 1; }
            VERSION="$1"; shift ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
TMP_WORKTREE="$(mktemp -d)"

cleanup() {
    git -C "$REPO_ROOT" worktree remove --force "$TMP_WORKTREE" 2>/dev/null || true
    rm -rf "$TMP_WORKTREE"
}
trap cleanup EXIT

if git -C "$REPO_ROOT" show-ref --quiet "refs/remotes/origin/$MAIN_REF"; then
    MAIN_REF="origin/$MAIN_REF"
fi

if [[ -n "$RC_TAG" ]]; then
    [[ -n "$VERSION" || -n "$COMMIT_MESSAGE" ]] && {
        echo "Error: --rc-tag carries the version and the message; drop --tag/--message." >&2; exit 1; }
    [[ "$RC_TAG" == *"$RC_SUFFIX" ]] || {
        echo "Error: release candidate tag '$RC_TAG' must end in '$RC_SUFFIX'." >&2; exit 1; }
    [[ "$(git -C "$REPO_ROOT" cat-file -t "$RC_TAG" 2>/dev/null)" == "tag" ]] || {
        echo "Error: '$RC_TAG' is not an annotated tag; its message is the release note." >&2; exit 1; }
    if [[ -z "$(git -C "$REPO_ROOT" for-each-ref "refs/tags/$RC_TAG" --format='%(contents:body)')" ]]; then
        echo "Error: tag '$RC_TAG' has no message body; a release must describe its changes." >&2
        exit 1
    fi
    if ! git -C "$REPO_ROOT" merge-base --is-ancestor "$RC_TAG^{commit}" "$MAIN_REF"; then
        echo "Error: tag '$RC_TAG' is not reachable from $MAIN_REF." >&2
        exit 1
    fi
    SOURCE_REF="$RC_TAG"
    VERSION="${RC_TAG%$RC_SUFFIX}"
    COMMIT_MESSAGE="$(git -C "$REPO_ROOT" for-each-ref "refs/tags/$RC_TAG" --format='%(contents)')"
fi

SOURCE_SHORT="$(git -C "$REPO_ROOT" rev-parse --short "${SOURCE_REF}^{commit}" 2>/dev/null)" \
    || { echo "Error: ref '$SOURCE_REF' not found." >&2; exit 1; }

echo "Source : $SOURCE_REF ($SOURCE_SHORT)"
echo "Target : $RELEASE_BRANCH"
[[ -n "$RC_TAG" ]] && echo "From   : $RC_TAG"
[[ -n "$VERSION" ]] && echo "Tag    : $VERSION"
echo ""

UNCLASSIFIED=""
while IFS= read -r entry; do
    for known in "${RELEASE_PATHS[@]}" "${DEV_PATHS[@]}"; do
        [[ "$entry" == "${known%%/*}" ]] && continue 2
    done
    UNCLASSIFIED="${UNCLASSIFIED}  $entry"$'\n'
done < <(git -C "$REPO_ROOT" ls-tree --name-only "$SOURCE_REF")

if [[ -n "$UNCLASSIFIED" ]]; then
    echo "Error: '$SOURCE_REF' has top-level entries that are in neither RELEASE_PATHS nor DEV_PATHS:" >&2
    printf '%s' "$UNCLASSIFIED" >&2
    echo "Add each one to the list it belongs to in $0." >&2
    exit 1
fi

# A stale local publish silently rebases the release onto the wrong base, so it
# is refused; origin is the base of record.
if git -C "$REPO_ROOT" show-ref --quiet "refs/remotes/origin/$RELEASE_BRANCH"; then
    REMOTE_HEAD="$(git -C "$REPO_ROOT" rev-parse "origin/$RELEASE_BRANCH")"
    if git -C "$REPO_ROOT" show-ref --quiet "refs/heads/$RELEASE_BRANCH"; then
        LOCAL_HEAD="$(git -C "$REPO_ROOT" rev-parse "$RELEASE_BRANCH")"
        if [[ "$LOCAL_HEAD" != "$REMOTE_HEAD" ]]; then
            echo "Error: local '$RELEASE_BRANCH' ($LOCAL_HEAD) differs from origin ($REMOTE_HEAD)." >&2
            echo "Fetch and run: git branch -f $RELEASE_BRANCH origin/$RELEASE_BRANCH" >&2
            exit 1
        fi
    else
        git -C "$REPO_ROOT" branch -q "$RELEASE_BRANCH" "origin/$RELEASE_BRANCH"
    fi
fi

if git -C "$REPO_ROOT" show-ref --quiet "refs/heads/$RELEASE_BRANCH"; then
    git -C "$REPO_ROOT" worktree add -q "$TMP_WORKTREE" "$RELEASE_BRANCH"
    git -C "$TMP_WORKTREE" rm -rf --quiet . 2>/dev/null || true
else
    git -C "$REPO_ROOT" worktree add -q --orphan -b "$RELEASE_BRANCH" "$TMP_WORKTREE"
fi

FOUND=0
EXPORT_PATHS=()
for path in "${RELEASE_PATHS[@]}"; do
    if git -C "$REPO_ROOT" cat-file -e "${SOURCE_REF}:${path}" 2>/dev/null; then
        EXPORT_PATHS+=("$path"); echo "  + $path"; FOUND=$((FOUND + 1))
    else
        echo "  - $path  (not in $SOURCE_REF, skipped)"
    fi
done

if [[ "$FOUND" -eq 0 ]]; then
    echo "" >&2; echo "Error: none of the release files were found in '$SOURCE_REF'." >&2; exit 1
fi

echo ""
git -C "$REPO_ROOT" archive "$SOURCE_REF" "${EXPORT_PATHS[@]}" | tar -x -C "$TMP_WORKTREE"
git -C "$TMP_WORKTREE" add -A

if git -C "$TMP_WORKTREE" diff --cached --quiet 2>/dev/null; then
    RELEASE_COMMIT="$(git -C "$TMP_WORKTREE" rev-parse HEAD)"
    PUBLISHED_SOURCE="$(git -C "$TMP_WORKTREE" log -1 --format='%(trailers:key=Source,valueonly)' | tr -d '[:space:]')"
    # Re-running the same release (a push that failed after the commit landed)
    # only needs the tag. A different source with nothing to publish means the
    # release changes nothing users receive.
    if [[ -n "$RC_TAG" && "$PUBLISHED_SOURCE" != "main@${SOURCE_SHORT}" ]]; then
        echo "Error: '$SOURCE_REF' changes nothing under RELEASE_PATHS; there is no release to publish." >&2
        exit 1
    fi
    echo "No changes: publish branch is already up to date."
    echo "HEAD : $RELEASE_COMMIT"
else
    # --rc-tag carries the summary written for this release; the fallback header
    # is only for a manual publish.
    COMMIT_MSG="${COMMIT_MESSAGE:-}"
    if [[ -z "$COMMIT_MSG" ]]; then
        if [[ -n "$VERSION" ]]; then
            COMMIT_MSG="publish: release $VERSION runtime plugin"
        else
            COMMIT_MSG="publish: release runtime plugin"
        fi
    fi
    COMMIT_MSG="${COMMIT_MSG}"$'\n\n'"Source: main@${SOURCE_SHORT}"
    git -C "$TMP_WORKTREE" commit -q -m "$COMMIT_MSG"
    RELEASE_COMMIT="$(git -C "$TMP_WORKTREE" rev-parse HEAD)"
    echo "Committed  : $RELEASE_COMMIT"
fi

if [[ -n "$VERSION" ]]; then
    git -C "$REPO_ROOT" tag -d "$VERSION" 2>/dev/null && echo "Removed existing tag '$VERSION'." || true
    if [[ -n "$RC_TAG" ]]; then
        git -C "$REPO_ROOT" tag -a "$VERSION" "$RELEASE_COMMIT" -m "$COMMIT_MESSAGE"
    else
        git -C "$REPO_ROOT" tag -a "$VERSION" "$RELEASE_COMMIT" -m "Release $VERSION"
    fi
    echo "Tagged     : $VERSION -> $RELEASE_COMMIT"
fi

echo ""
echo "Push with:"
echo "  git push origin $RELEASE_BRANCH"
[[ -n "$VERSION" ]] && echo "  git push origin refs/tags/$VERSION"
