#!/usr/bin/env bash
# Create or update a shadow pull request on the fork for a pull request opened
# against the upstream repository, so the review bot can be run on the fork.
#
#   ./shadow-pr.sh <upstream-pr-number> [--base <branch>] [--dry-run]
#   ./shadow-pr.sh clear [--dry-run]
#
# `clear` closes every open shadow PR on the fork whose upstream PR is no longer
# open (merged or closed). Shadow PRs whose body carries no upstream marker, or
# whose upstream cannot be read, are reported and left alone. The
# `shadow/pr-<n>` branches are kept, so a later upstream revision can still be
# reviewed without copying the head again.
#
# The original head is copied to a `shadow/pr-<n>` branch on the fork, because
# GitHub does not let one person open a pull request whose head is somebody
# else's fork. The shadow PR therefore lives entirely in the fork: base is the
# fork's base branch (default: the original PR's base branch, falling back to
# main) and head is `shadow/pr-<n>`, which is refreshed on every run.
#
# The shadow PR body carries a marker and a link to the original pull request.
# The marker is how an existing shadow PR is found, so re-running the script
# updates that PR instead of opening a duplicate, and tracks later revisions of
# the original title, description and commits.
set -euo pipefail

UPSTREAM_REPO=${UPSTREAM_REPO:-RLinf/RPent}
UPSTREAM_URL=${UPSTREAM_URL:-https://ghfast.top/github.com/$UPSTREAM_REPO.git}
FORK_REPO=${FORK_REPO:-qurakchin/RPent}
FORK_REMOTE=${FORK_REMOTE:-origin}
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

usage() {
  # The leading comment block, without the `# ` prefixes; stops at the first
  # line of code, so adding header lines does not shift a line range.
  awk 'NR > 1 && /^set -euo/ { exit } NR > 1 { sub(/^# ?/, ""); print }' "${BASH_SOURCE[0]}"
  exit "${1:-1}"
}

mode=create
if [ $# -gt 0 ] && [ "$1" = clear ]; then
  mode=clear
  shift
fi

pr=""
base=""
dry_run=false
while [ $# -gt 0 ]; do
  case $1 in
    -h | --help) usage 0 ;;
    --base) base=${2:?--base needs a value}; shift 2 ;;
    --dry-run) dry_run=true; shift ;;
    -*) echo "unknown option: $1" >&2; usage ;;
    *)
      if [ -n "$pr" ]; then echo "unexpected argument: $1" >&2; usage; fi
      pr=$1
      shift
      ;;
  esac
done
if [ "$mode" = clear ]; then
  [ -z "$pr" ] || { echo "clear takes no PR number: $pr" >&2; usage; }
  [ -z "$base" ] || { echo "clear does not take --base" >&2; usage; }
else
  [ -n "$pr" ] || usage
fi

command -v gh >/dev/null || { echo "gh is required" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "gh is not authenticated" >&2; exit 1; }

run() {
  if $dry_run; then
    printf '+ %s\n' "$*"
  else
    "$@"
  fi
}

if [ "$mode" = clear ]; then
  # --- clear: close shadow PRs whose upstream is no longer open ---------------
  # The marker in the shadow body names the original PR; that is the only link
  # back, so a shadow without one cannot be judged and is left open.
  shadows=$(gh pr list --repo "$FORK_REPO" --state open --limit 200 \
    --json number,body |
    jq -r '.[] | [.number,
      (try ((.body // "") | capture("shadow-of: [^#]+#(?<n>[0-9]+)").n) catch "")] | @tsv')

  closed=0
  open=0
  skipped=0
  while IFS=$'\t' read -r number upstream; do
    [ -n "${number:-}" ] || continue
    if [ -z "$upstream" ]; then
      echo "skip $FORK_REPO#$number: no upstream marker in the body" >&2
      skipped=$((skipped + 1))
      continue
    fi
    if ! state=$(gh pr view "$upstream" --repo "$UPSTREAM_REPO" --json state --jq .state 2>/dev/null); then
      echo "skip $FORK_REPO#$number: cannot read $UPSTREAM_REPO#$upstream" >&2
      skipped=$((skipped + 1))
      continue
    fi
    case $state in
      OPEN)
        open=$((open + 1))
        ;;
      MERGED | CLOSED)
        echo "closing $FORK_REPO#$number: $UPSTREAM_REPO#$upstream is $state"
        run gh pr close "$number" --repo "$FORK_REPO"
        closed=$((closed + 1))
        ;;
      *)
        echo "skip $FORK_REPO#$number: $UPSTREAM_REPO#$upstream is $state" >&2
        skipped=$((skipped + 1))
        ;;
    esac
  done <<<"$shadows"

  echo
  if $dry_run; then
    echo "dry run: nothing was closed"
  else
    echo "closed $closed shadow PR(s)"
  fi
  echo "kept: $open upstream still open, $skipped skipped"
  exit 0
fi

# Every push goes to the fork; refuse to run if the remote points elsewhere.
push_url=$(git -C "$HERE" remote get-url --push "$FORK_REMOTE" 2>/dev/null || printf '%s' "$FORK_REMOTE")
case $push_url in
  *"$FORK_REPO"*) ;;
  *)
    echo "refusing: $FORK_REMOTE pushes to '$push_url', expected $FORK_REPO" >&2
    exit 1
    ;;
esac

# --- original pull request ---------------------------------------------------
original=$(gh pr view "$pr" --repo "$UPSTREAM_REPO" \
  --json title,body,url,state,baseRefName,headRefName,headRefOid,headRepository,headRepositoryOwner)

field() { jq -r "$1" <<<"$original"; }
orig_title=$(field .title)
orig_body=$(field '.body // ""')
orig_url=$(field .url)
orig_state=$(field .state)
orig_base=$(field .baseRefName)
head_ref=$(field .headRefName)
head_sha=$(field .headRefOid)
head_full=$(field .headRepository.nameWithOwner)

if [ "$orig_state" != OPEN ]; then
  echo "warning: $UPSTREAM_REPO#$pr is $orig_state; the shadow PR will not receive new commits" >&2
fi

# --- shadow base branch ------------------------------------------------------
if [ -z "$base" ]; then
  base=$orig_base
  if ! gh api "repos/$FORK_REPO/branches/$base" >/dev/null 2>&1; then
    echo "warning: $FORK_REPO has no branch '$base'; using main" >&2
    base=main
  fi
fi

# --- shadow head branch ------------------------------------------------------
# `refs/pull/<n>/head` exists in the upstream repository for every pull
# request, including ones whose head is another fork, so it is a uniform source
# for the shadow branch.
if [ "$head_full" = "$FORK_REPO" ]; then
  head_arg=$head_ref
else
  head_arg=shadow/pr-$pr
  run git -C "$HERE" fetch --force "$UPSTREAM_URL" \
    "refs/pull/$pr/head:refs/heads/$head_arg"
  run git -C "$HERE" push --force "$FORK_REMOTE" \
    "refs/heads/$head_arg:refs/heads/$head_arg"
  if ! $dry_run; then
    fetched=$(git -C "$HERE" rev-parse "refs/heads/$head_arg")
    if [ "$fetched" != "$head_sha" ]; then
      echo "warning: copied $fetched but $UPSTREAM_REPO#$pr reports head $head_sha" >&2
    fi
  fi
fi

# --- existing shadow PR ------------------------------------------------------
marker="<!-- shadow-of: $UPSTREAM_REPO#$pr -->"
existing=$(gh pr list --repo "$FORK_REPO" --state all --limit 200 \
  --json number,state,headRefName,url,body |
  jq -c --arg marker "$marker" '
    [.[] | select((.body // "") | contains($marker))] | sort_by(.number) |
    if length > 0 then (last + {count: length}) else empty end')

if [ -n "$existing" ]; then
  existing_count=$(jq -r .count <<<"$existing")
  if [ "$existing_count" -gt 1 ]; then
    echo "warning: $existing_count shadow PRs carry the marker; updating the highest-numbered one" >&2
  fi
fi

# --- title and body ----------------------------------------------------------
title="[shadow #$pr] $orig_title"
short_sha=${head_sha:0:12}
# The backticks are markdown for the rendered body, not command substitution.
# shellcheck disable=SC2016
body=$(printf '%s\n\n> Shadow of [%s#%s](%s) (`%s:%s` @ `%s`). Opened by shadow-pr.sh for review; **do not merge**.\n\n%s\n\n---\n*Generated by shadow-pr.sh; this body is rewritten on every run.*\n' \
  "$marker" "$UPSTREAM_REPO" "$pr" "$orig_url" "$head_full" "$head_ref" "$short_sha" "$orig_body")

body_file=$(mktemp)
trap 'rm -f "$body_file"' EXIT
printf '%s' "$body" >"$body_file"

# --- create or update --------------------------------------------------------
if [ -n "$existing" ]; then
  number=$(jq -r .number <<<"$existing")
  state=$(jq -r .state <<<"$existing")
  old_head=$(jq -r .headRefName <<<"$existing")

  if [ "$old_head" != "$head_arg" ]; then
    echo "warning: the shadow PR tracks '$old_head' but this run uses '$head_arg'" >&2
    echo "warning: an existing PR's head branch cannot be changed; close it manually if the head moved" >&2
  fi
  if [ "$state" != OPEN ]; then
    echo "reopening $FORK_REPO#$number ($state)"
    run gh pr reopen "$number" --repo "$FORK_REPO"
  fi
  echo "updating $FORK_REPO#$number"
  run gh pr edit "$number" --repo "$FORK_REPO" --title "$title" --body-file "$body_file"
  shadow_url=$(gh pr view "$number" --repo "$FORK_REPO" --json url --jq .url)
else
  echo "creating a shadow PR on $FORK_REPO for $UPSTREAM_REPO#$pr"
  number=""
  if $dry_run; then
    run gh pr create --repo "$FORK_REPO" --base "$base" --head "$head_arg" \
      --title "$title" --body-file "$body_file"
    shadow_url=""
  else
    shadow_url=$(gh pr create --repo "$FORK_REPO" --base "$base" --head "$head_arg" \
      --title "$title" --body-file "$body_file")
    number=$(printf '%s' "$shadow_url" | sed -n 's#.*/pull/\([0-9][0-9]*\).*#\1#p')
  fi
fi

echo
if $dry_run; then
  echo "dry run: nothing was changed"
else
  echo "shadow PR: $shadow_url"
  echo "next:      gh pr comment ${number:-<number>} --repo $FORK_REPO --body '/review-design'"
fi
