#!/usr/bin/env bash
set -euo pipefail

# Manage git worktrees named by ticket number.
#
# Worktrees live inside the repo under .worktrees/ (gitignored) so the main
# checkout stays on `main` and coding tools only need write permission for one
# directory tree. Each worktree gets its own branch of the form `ticket/<n>` or
# `ticket/<n>-<short-desc>`, based off the latest `origin/main`.
#
# Usage:
#   scripts/worktree.sh start <ticket> [short-description]
#   scripts/worktree.sh list
#   scripts/worktree.sh stop <ticket>
#   scripts/worktree.sh done <ticket>

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKTREE_ROOT="$ROOT/.worktrees"

usage() {
  cat <<EOF
Usage: scripts/worktree.sh <command> [args]

Commands:
  start <ticket> [desc]   Create a worktree at .worktrees/<ticket> on branch ticket/<ticket>[-<desc>]
  list                    List all worktrees for this repo
  stop <ticket>           Remove the worktree and its local branch
  done <ticket>           Remove worktree + local branch + remote branch (after PR merge)

Worktrees live under .worktrees/ inside the repo (gitignored) so the main
checkout stays on main and coding tools only need write access to one tree.
EOF
}

slugify() {
  local desc="$1"
  echo "$desc" | tr '[:upper:]' '[:lower:]' | tr -c '[:alnum:]' '-' | sed 's/--*/-/g' | sed 's/^-//;s/-$//'
}

branch_for_ticket() {
  local ticket="$1"
  git -C "$ROOT" branch --list "ticket/${ticket}" "ticket/${ticket}-*" --format='%(refname:short)' | head -1
}

cmd="${1:-}"
shift || true

case "$cmd" in
  -h|--help) usage; exit 0 ;;
  start)
    ticket="${1:?ticket number required, e.g. 6}"
    desc="${2:-}"
    branch="ticket/${ticket}"
    if [[ -n "$desc" ]]; then
      branch="ticket/${ticket}-$(slugify "$desc")"
    fi
    target="$WORKTREE_ROOT/$ticket"
    if [[ -e "$target" ]]; then
      echo "error: worktree target already exists: $target" >&2
      exit 1
    fi
    mkdir -p "$WORKTREE_ROOT"
    git -C "$ROOT" fetch origin main --prune
    git -C "$ROOT" worktree add -b "$branch" "$target" origin/main
    echo
    echo "worktree ready:"
    echo "  path:   $target"
    echo "  branch: $branch"
    echo "  cd:     cd \"$target\""
    ;;
  list)
    git -C "$ROOT" worktree list
    ;;
  stop)
    ticket="${1:?ticket number required}"
    target="$WORKTREE_ROOT/$ticket"
    branch="$(branch_for_ticket "$ticket")"
    git -C "$ROOT" worktree remove "$target" --force 2>/dev/null || true
    if [[ -n "$branch" ]]; then
      git -C "$ROOT" branch -D "$branch" 2>/dev/null || true
    fi
    echo "removed worktree and local branch for ticket $ticket"
    ;;
  done)
    ticket="${1:?ticket number required}"
    target="$WORKTREE_ROOT/$ticket"
    branch="$(branch_for_ticket "$ticket")"
    git -C "$ROOT" worktree remove "$target" --force 2>/dev/null || true
    if [[ -n "$branch" ]]; then
      git -C "$ROOT" branch -D "$branch" 2>/dev/null || true
      git -C "$ROOT" push origin --delete "$branch" 2>/dev/null || true
    fi
    echo "cleaned up ticket $ticket (worktree + local branch + remote branch)"
    ;;
  *) usage >&2; exit 2 ;;
esac
