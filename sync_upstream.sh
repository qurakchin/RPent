#!/usr/bin/env bash
# Rebase the fork's long-lived branches onto upstream main.
#
#   ./sync_upstream.sh [--dry-run] [--no-push] [branch...]
#
# Default branches: main review. A branch must exist locally or on the fork
# remote; one that exists in neither is skipped. Commits that upstream main
# does not contain are replayed on top of it and the result is pushed to the
# fork with --force-with-lease. If the rebase conflicts, it is left in progress
# on that branch so it can be resolved with git rebase --continue or --abort.
set -euo pipefail

UPSTREAM_URL=${UPSTREAM_URL:-https://ghfast.top/github.com/RLinf/RPent.git}
UPSTREAM_BRANCH=${UPSTREAM_BRANCH:-main}
FORK_REPO=${FORK_REPO:-qurakchin/RPent}
FORK_REMOTE=${FORK_REMOTE:-origin}
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

usage() {
  sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit "${1:-1}"
}

branches=()
dry_run=false
push=true
while [ $# -gt 0 ]; do
  case $1 in
    -h | --help) usage 0 ;;
    --dry-run) dry_run=true; shift ;;
    --no-push) push=false; shift ;;
    -*) echo "unknown option: $1" >&2; usage ;;
    *) branches+=("$1"); shift ;;
  esac
done
[ ${#branches[@]} -gt 0 ] || branches=(main review)

cd "$HERE"
git rev-parse --git-dir >/dev/null 2>&1 || { echo "$HERE is not a git repository" >&2; exit 1; }

# Everything here is pushed to the fork; refuse to run if that remote is not it.
push_url=$(git remote get-url --push "$FORK_REMOTE" 2>/dev/null || printf '%s' "$FORK_REMOTE")
case $push_url in
  *"$FORK_REPO"*) ;;
  *)
    echo "refusing: $FORK_REMOTE pushes to '$push_url', expected $FORK_REPO" >&2
    exit 1
    ;;
esac

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "the working tree has uncommitted changes; commit or stash them first:" >&2
  git status --short --untracked-files=no >&2
  exit 1
fi
if [ -d "$(git rev-parse --git-path rebase-merge)" ] || [ -d "$(git rev-parse --git-path rebase-apply)" ]; then
  echo "a rebase is already in progress; finish or abort it first" >&2
  exit 1
fi
original=$(git symbolic-ref --quiet --short HEAD || true)

upstream_ref=refs/upstream-sync/$UPSTREAM_BRANCH
echo "fetching $UPSTREAM_BRANCH from $UPSTREAM_URL"
if ! git fetch --quiet --force --no-tags "$UPSTREAM_URL" "+refs/heads/$UPSTREAM_BRANCH:$upstream_ref"; then
  echo "failed to fetch $UPSTREAM_BRANCH from $UPSTREAM_URL" >&2
  exit 1
fi
upstream_tip=$(git rev-parse "$upstream_ref")
echo "upstream $UPSTREAM_BRANCH is $(git rev-parse --short "$upstream_tip")"

push_new_branch() {
  if $dry_run; then
    printf '+ git push %s %s:%s\n' "$FORK_REMOTE" "$1" "$1"
  else
    git push "$FORK_REMOTE" "$1:$1"
  fi
}

failed=0
for b in "${branches[@]}"; do
  if ! git show-ref --verify --quiet "refs/heads/$b"; then
    if git fetch --quiet --no-tags "$FORK_REMOTE" "+refs/heads/$b:refs/heads/$b" 2>/dev/null; then
      echo "$b: fetched from $FORK_REMOTE"
    else
      echo "skip $b: not found locally or on $FORK_REMOTE" >&2
      continue
    fi
  fi

  if git merge-base --is-ancestor "$upstream_tip" "refs/heads/$b"; then
    echo "$b: already contains upstream $UPSTREAM_BRANCH"
    if $push && ! git ls-remote --exit-code --heads "$FORK_REMOTE" "$b" >/dev/null 2>&1; then
      echo "$b: creating $b on $FORK_REMOTE at $(git rev-parse --short "refs/heads/$b")"
      push_new_branch "$b"
    fi
    continue
  fi

  ahead=$(git rev-list --count "$upstream_tip..refs/heads/$b")
  behind=$(git rev-list --count "refs/heads/$b..$upstream_tip")
  old=$(git rev-parse --short "refs/heads/$b")
  echo "$b: replaying $ahead local commit(s) onto upstream ($behind new upstream commit(s))"

  if $dry_run; then
    printf '+ git checkout %s\n' "$b"
    printf '+ git rebase %s\n' "$upstream_tip"
    $push && printf '+ git push --force-with-lease %s %s:%s\n' "$FORK_REMOTE" "$b" "$b"
    continue
  fi

  git checkout --quiet "$b"
  if ! git rebase "$upstream_tip"; then
    echo >&2
    echo "conflict while rebasing $b; the rebase is left in progress. Either" >&2
    echo "  git rebase --continue   # finish it after resolving the conflicts" >&2
    echo "  git rebase --abort      # drop the rebase and keep the branch as it was" >&2
    failed=1
    break
  fi

  if $push; then
    if git ls-remote --exit-code --heads "$FORK_REMOTE" "$b" >/dev/null 2>&1; then
      git fetch --quiet --no-tags "$FORK_REMOTE" "+refs/heads/$b:refs/remotes/$FORK_REMOTE/$b" || true
      git push --force-with-lease "$FORK_REMOTE" "$b:$b"
    else
      echo "$b: creating $b on $FORK_REMOTE"
      git push "$FORK_REMOTE" "$b:$b"
    fi
  else
    echo "$b: rebased locally, not pushed (--no-push)"
  fi
  echo "$b: $old -> $(git rev-parse --short "refs/heads/$b")"
done

if [ "$failed" -eq 0 ] && [ -n "$original" ] && [ "$(git symbolic-ref --quiet --short HEAD || true)" != "$original" ]; then
  git checkout --quiet "$original"
  echo "back on $original"
fi
exit "$failed"
