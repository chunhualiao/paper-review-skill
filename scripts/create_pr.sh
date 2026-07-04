#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/create_pr.sh check-body <body-file>
  scripts/create_pr.sh verify-body <repo> <pr-number-or-url>
  scripts/create_pr.sh create --repo <owner/name> --base <branch> --head <branch> --title <title> --body-file <path|->

Creates pull requests with real Markdown bodies and rejects literal "\n" escape
sequences before and after PR creation.
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

check_body_file() {
  local body_file="$1"
  [[ -f "$body_file" ]] || die "body file not found: $body_file"
  [[ -s "$body_file" ]] || die "body file is empty: $body_file"
  if grep -q '\\n' "$body_file"; then
    die 'PR body contains literal \n escape sequences; use real Markdown newlines'
  fi
}

verify_pr_body() {
  local repo="$1"
  local pr="$2"
  local body
  body="$(gh pr view "$pr" --repo "$repo" --json body --jq .body)"
  if grep -q '\\n' <<<"$body"; then
    die "created PR body contains literal \\n escape sequences: $pr"
  fi
}

cmd="${1:-}"
shift || true

case "$cmd" in
  -h|--help)
    usage
    ;;
  check-body)
    [[ $# -eq 1 ]] || die "check-body requires exactly one body file"
    check_body_file "$1"
    ;;
  verify-body)
    [[ $# -eq 2 ]] || die "verify-body requires <repo> and <pr-number-or-url>"
    verify_pr_body "$1" "$2"
    ;;
  create)
    repo=""
    base=""
    head=""
    title=""
    body_file=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --repo)
          repo="${2:?--repo requires a value}"
          shift 2
          ;;
        --base)
          base="${2:?--base requires a value}"
          shift 2
          ;;
        --head)
          head="${2:?--head requires a value}"
          shift 2
          ;;
        --title)
          title="${2:?--title requires a value}"
          shift 2
          ;;
        --body-file)
          body_file="${2:?--body-file requires a value}"
          shift 2
          ;;
        --body)
          die 'do not pass PR Markdown with --body; use --body-file <path|->'
          ;;
        *)
          die "unknown argument: $1"
          ;;
      esac
    done

    [[ -n "$repo" ]] || die "--repo is required"
    [[ -n "$base" ]] || die "--base is required"
    [[ -n "$head" ]] || die "--head is required"
    [[ -n "$title" ]] || die "--title is required"
    [[ -n "$body_file" ]] || die "--body-file is required"

    tmp_body=""
    if [[ "$body_file" == "-" ]]; then
      tmp_body="$(mktemp)"
      cat >"$tmp_body"
      body_file="$tmp_body"
    fi
    trap '[[ -z "${tmp_body:-}" ]] || rm -f "$tmp_body"' EXIT

    check_body_file "$body_file"
    pr_url="$(
      gh pr create \
        --repo "$repo" \
        --base "$base" \
        --head "$head" \
        --title "$title" \
        --body-file "$body_file"
    )"
    verify_pr_body "$repo" "$pr_url"
    echo "$pr_url"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
