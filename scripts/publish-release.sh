#!/usr/bin/env bash
# Publish minimum runtime plugin files from main HEAD to the publish branch.
# Requires Git >= 2.15 (git worktree add --orphan).
#
# Usage:
#   ./scripts/publish-release.sh [<version-tag>]
#
# Examples:
#   ./scripts/publish-release.sh           # update publish branch only
#   ./scripts/publish-release.sh v1.2.0    # update publish branch + create annotated tag
set -euo pipefail

# Paths included in the publish branch (no docs/, tests/, scripts/, deploy/).
RELEASE_PATHS=(
    plugin.yaml
    __init__.py
    adapter.py
    hermes_seatalk
    pyproject.toml
    requirements.txt
    env.example
    README.md
)

RELEASE_BRANCH="publish"
SOURCE_REF="main"
VERSION="${1:-}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
TMP_WORKTREE="$(mktemp -d)"

cleanup() {
    git -C "$REPO_ROOT" worktree remove --force "$TMP_WORKTREE" 2>/dev/null || true
    rm -rf "$TMP_WORKTREE"
}
trap cleanup EXIT

# Validate source ref exists.
SOURCE_SHORT="$(git -C "$REPO_ROOT" rev-parse --short "$SOURCE_REF" 2>/dev/null)" \
    || { echo "Error: branch '$SOURCE_REF' not found." >&2; exit 1; }

echo "Source : $SOURCE_REF ($SOURCE_SHORT)"
echo "Target : $RELEASE_BRANCH"
[[ -n "$VERSION" ]] && echo "Tag    : $VERSION"
echo ""

# Prepare worktree on the release branch (orphan if first publish).
if git -C "$REPO_ROOT" show-ref --quiet "refs/heads/$RELEASE_BRANCH"; then
    git -C "$REPO_ROOT" worktree add -q "$TMP_WORKTREE" "$RELEASE_BRANCH"
    # Clear existing content so removed files don't linger.
    git -C "$TMP_WORKTREE" rm -rf --quiet . 2>/dev/null || true
else
    git -C "$REPO_ROOT" worktree add -q --orphan -b "$RELEASE_BRANCH" "$TMP_WORKTREE"
fi

# Export each release path from SOURCE_REF HEAD.
FOUND=0
EXPORT_PATHS=()
for path in "${RELEASE_PATHS[@]}"; do
    if git -C "$REPO_ROOT" cat-file -e "${SOURCE_REF}:${path}" 2>/dev/null; then
        EXPORT_PATHS+=("$path")
        echo "  + $path"
        FOUND=$((FOUND + 1))
    else
        echo "  - $path  (not in $SOURCE_REF, skipped)"
    fi
done

if [[ "$FOUND" -eq 0 ]]; then
    echo "" >&2
    echo "Error: none of the release files were found in '$SOURCE_REF'." >&2
    exit 1
fi

echo ""
git -C "$REPO_ROOT" archive "$SOURCE_REF" "${EXPORT_PATHS[@]}" | tar -x -C "$TMP_WORKTREE"
git -C "$TMP_WORKTREE" add -A

# Commit only when content actually changed.
if git -C "$TMP_WORKTREE" diff --cached --quiet 2>/dev/null; then
    RELEASE_COMMIT="$(git -C "$TMP_WORKTREE" rev-parse HEAD)"
    echo "No changes — publish branch is already up to date."
    echo "HEAD : $RELEASE_COMMIT"
else
    COMMIT_MSG="publish: publish runtime plugin files"
    [[ -n "$VERSION" ]] && COMMIT_MSG="$COMMIT_MSG ($VERSION)"
    git -C "$TMP_WORKTREE" commit -q -m "$COMMIT_MSG"
    RELEASE_COMMIT="$(git -C "$TMP_WORKTREE" rev-parse HEAD)"
    echo "Committed  : $RELEASE_COMMIT"
fi

# Create (or replace) the version tag on the release commit.
if [[ -n "$VERSION" ]]; then
    if git -C "$REPO_ROOT" tag -d "$VERSION" 2>/dev/null; then
        echo "Removed existing tag '$VERSION'."
    fi
    git -C "$REPO_ROOT" tag -a "$VERSION" "$RELEASE_COMMIT" -m "Release $VERSION"
    echo "Tagged     : $VERSION → $RELEASE_COMMIT"
fi

echo ""
echo "Push with:"
echo "  git push origin $RELEASE_BRANCH"
if [[ -n "$VERSION" ]]; then
    echo "  git push origin refs/tags/$VERSION"
fi
