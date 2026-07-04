#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER="$ROOT/scripts/html_explain_server.py"
POLICY_WRAPPER="$ROOT/scripts/codex_exec_with_policy.py"

case "${1:-}" in
  -h|--help)
    cat <<EOF
Usage: scripts/start_html_explainer.sh --root <dir> [--paper <paper.pdf>] [--review-html <review.html>] [server options]

Start the live paper-review explainer using the model-policy Codex wrapper.

Common options are passed through to scripts/html_explain_server.py:
  --root <dir>          Root directory served by the explainer. For multi-paper batches, use the shared parent directory and omit --paper/--review-html.
  --paper <paper.pdf>   Paper PDF under --root for single-paper mode
  --review-html <html>  Rendered review HTML under --root for single-paper mode
  --host <host>         Default: 127.0.0.1
  --port <port>         Default: 8765
EOF
    exit 0
    ;;
esac

[[ -f "$SERVER" ]] || { echo "error: missing explainer server: $SERVER" >&2; exit 1; }
[[ -x "$POLICY_WRAPPER" ]] || { echo "error: missing model-policy Codex wrapper: $POLICY_WRAPPER" >&2; exit 1; }

export PAPER_REVIEW_CODEX_STAGE="${PAPER_REVIEW_CODEX_STAGE:-explainer.qa}"
export CODEX_EXEC_BIN="${CODEX_EXEC_BIN:-$POLICY_WRAPPER}"

model="$(python3 "$ROOT/scripts/model_policy.py" --stage "$PAPER_REVIEW_CODEX_STAGE" --field model)"
thinking="$(python3 "$ROOT/scripts/model_policy.py" --stage "$PAPER_REVIEW_CODEX_STAGE" --field thinking)"

echo "Starting live explainer with model=$model thinking_level=$thinking"
exec python3 "$SERVER" "$@"
