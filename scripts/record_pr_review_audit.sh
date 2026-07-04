#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/record_pr_review_audit.sh --repo <owner/name> --pr <number> --status <status> [--wait-seconds <n>] [--notes-file <path|->]

Posts a PR comment proving that GitHub bot review threads were checked and
summarizing whether they were acted on.

Statuses:
  no-comments       No unresolved, non-outdated review threads were present.
  addressed         Actionable review comments were implemented or otherwise resolved.
  responded         Review comments were answered but did not require code/docs changes.
  deferred          Review comments were intentionally deferred; explain why in notes.

Use --notes-file for validation commands, links to commits, or rationale. Use
--notes-file - to read notes from stdin.
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

repo=""
pr=""
status=""
wait_seconds=60
notes_file=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --repo)
      repo="${2:?--repo requires a value}"
      shift 2
      ;;
    --pr)
      pr="${2:?--pr requires a value}"
      shift 2
      ;;
    --status)
      status="${2:?--status requires a value}"
      shift 2
      ;;
    --wait-seconds)
      wait_seconds="${2:?--wait-seconds requires a value}"
      shift 2
      ;;
    --notes-file)
      notes_file="${2:?--notes-file requires a value}"
      shift 2
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[[ -n "$repo" ]] || die "--repo is required"
[[ -n "$pr" ]] || die "--pr is required"
[[ "$pr" =~ ^[0-9]+$ ]] || die "--pr must be a number"
[[ "$wait_seconds" =~ ^[0-9]+$ ]] || die "--wait-seconds must be a non-negative integer"

case "$status" in
  no-comments|addressed|responded|deferred) ;;
  *) die "--status must be one of: no-comments, addressed, responded, deferred" ;;
esac

if [[ "$wait_seconds" != "0" ]]; then
  sleep "$wait_seconds"
fi

owner="${repo%%/*}"
name="${repo#*/}"
[[ "$owner" != "$repo" && -n "$name" ]] || die "--repo must look like owner/name"

summary_json="$(
  python3 - "$owner" "$name" "$pr" <<'PY'
import json
import subprocess
import sys

owner, name, number = sys.argv[1], sys.argv[2], sys.argv[3]
query = """query($owner:String!, $name:String!, $number:Int!, $cursor:String) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      reviewThreads(first:100, after:$cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          isResolved
          isOutdated
          path
          line
          comments(first:20) {
            nodes {
              author { login }
              body
              url
            }
          }
        }
      }
    }
  }
}"""

threads = []
cursor = None
while True:
    command = [
        "gh",
        "api",
        "graphql",
        "-f",
        f"owner={owner}",
        "-f",
        f"name={name}",
        "-F",
        f"number={number}",
        "-f",
        f"query={query}",
    ]
    if cursor:
        command.extend(["-f", f"cursor={cursor}"])
    payload = json.loads(subprocess.check_output(command, text=True))
    page = payload["data"]["repository"]["pullRequest"]["reviewThreads"]
    threads.extend(page["nodes"])
    if not page["pageInfo"]["hasNextPage"]:
        break
    cursor = page["pageInfo"]["endCursor"]

active = [thread for thread in threads if not thread.get("isResolved") and not thread.get("isOutdated")]
authors = sorted({
    comment.get("author", {}).get("login", "unknown")
    for thread in active
    for comment in thread.get("comments", {}).get("nodes", [])
})
paths = sorted({thread.get("path") or "unknown" for thread in active})
print(json.dumps({"active_count": len(active), "authors": authors, "paths": paths, "thread_count": len(threads)}))
PY
)"

active_count="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["active_count"])' <<<"$summary_json")"
thread_count="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["thread_count"])' <<<"$summary_json")"
authors="$(python3 -c 'import json,sys; data=json.load(sys.stdin); print(", ".join(data["authors"]) or "none")' <<<"$summary_json")"
paths="$(python3 -c 'import json,sys; data=json.load(sys.stdin); print(", ".join(data["paths"]) or "none")' <<<"$summary_json")"

notes=""
if [[ -n "$notes_file" ]]; then
  if [[ "$notes_file" == "-" ]]; then
    notes="$(cat)"
  else
    [[ -f "$notes_file" ]] || die "notes file not found: $notes_file"
    notes="$(cat "$notes_file")"
  fi
fi

tmp_body="$(mktemp)"
trap 'rm -f "$tmp_body"' EXIT
{
  echo "## Bot review audit"
  echo
  echo "- Checked review threads: yes"
  echo "- Total review threads scanned: $thread_count"
  echo "- Unresolved, non-outdated threads: $active_count"
  echo "- Review authors seen: $authors"
  echo "- Paths with active threads: $paths"
  echo "- Action status: $status"
  if [[ -n "$notes" ]]; then
    echo
    echo "Notes:"
    echo "$notes"
  fi
} >"$tmp_body"

gh pr comment "$pr" --repo "$repo" --body-file "$tmp_body"
