#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER="$ROOT/scripts/html_explain_server.py"
DEFAULT_CODEX_MODEL="${PAPER_REVIEW_CODEX_MODEL:-${CODEX_MODEL:-gpt-5.5}}"
DEFAULT_EXPLAINER_THINKING="${PAPER_REVIEW_THINKING_EXPLAINER_QA:-high}"
DEEP_CHECK=0

case "${1:-}" in
  -h|--help)
    cat <<EOF
Usage: scripts/check_html_explainer_required.sh

Verify that the live paper-review HTML explainer can start.

Checks:
  - python3 and scripts/html_explain_server.py
  - one explainer backend: codex, OPENAI_API_KEY, or OLLAMA_MODEL
  - local HTTP server startup and index response
  - /api/review-question response path using an explicit test response

Options:
  --deep   Also verify the default Codex backend can answer a fixed prompt.

Environment:
  HTML_EXPLAIN_SKIP_BACKEND_PREFLIGHT=1   Skip --deep backend model call.
EOF
    exit 0
    ;;
  --deep)
    DEEP_CHECK=1
    shift
    ;;
esac

if [[ $# -gt 0 ]]; then
  echo "error: unknown argument: $1" >&2
  exit 2
fi

[[ -f "$SERVER" ]] || { echo "error: missing $SERVER" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "error: python3 is required" >&2; exit 1; }
python3 -m py_compile "$SERVER"

if [[ -z "${OPENAI_API_KEY:-}" && -z "${OLLAMA_MODEL:-}" ]] && ! command -v "${CODEX_EXEC_BIN:-codex}" >/dev/null 2>&1; then
  echo "error: mandatory explainer server needs codex, OPENAI_API_KEY, or OLLAMA_MODEL" >&2
  exit 1
fi

TMP_ROOT="$(mktemp -d)"
PID=""
cleanup() {
  if [[ -n "$PID" ]] && kill -0 "$PID" >/dev/null 2>&1; then
    kill "$PID" >/dev/null 2>&1 || true
    wait "$PID" >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

cat > "$TMP_ROOT/report.html" <<'HTML'
<!doctype html><html><body><section id="reviewer-follow-ups"><div id="review-qa-list"></div></section><h1>preflight</h1></body></html>
HTML
PORT="$(python3 - <<'PY'
import socket
s=socket.socket()
s.bind(("127.0.0.1",0))
print(s.getsockname()[1])
s.close()
PY
)"
HTML_EXPLAIN_TEST_RESPONSE="html-explainer-test-response" \
  python3 "$SERVER" --root "$TMP_ROOT" --host 127.0.0.1 --port "$PORT" >"$TMP_ROOT/server.log" 2>&1 &
PID="$!"
python3 - "$PORT" <<'PY'
import sys, time, urllib.request
url=f"http://127.0.0.1:{sys.argv[1]}/"
last=None
for _ in range(50):
    try:
        with urllib.request.urlopen(url, timeout=.25) as r:
            text=r.read().decode()
            if r.status == 200 and "Paper Review Explainer" in text:
                raise SystemExit(0)
    except Exception as e:
        last=e
    time.sleep(.1)
raise SystemExit(f"server did not respond: {last}")
PY

python3 - "$PORT" <<'PY'
import json
import sys
import urllib.request

port = sys.argv[1]
payload = {
    "question": "preflight question",
    "page_text": "preflight review context",
    "path": "report.html",
}
request = urllib.request.Request(
    f"http://127.0.0.1:{port}/api/review-question",
    data=json.dumps(payload).encode("utf-8"),
    headers={"content-type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(request, timeout=5) as response:
    body = json.loads(response.read().decode("utf-8"))
if response.status != 200 or body.get("answer") != "html-explainer-test-response":
    raise SystemExit(f"question endpoint preflight failed: {body}")
PY

if [[ "$DEEP_CHECK" == "1" && "${HTML_EXPLAIN_SKIP_BACKEND_PREFLIGHT:-0}" != "1" ]]; then
  if [[ -n "${OPENAI_API_KEY:-}" || -n "${OLLAMA_MODEL:-}" ]]; then
    echo "HTML explainer deep backend preflight skipped: only Codex backend sanity is implemented"
  else
    TMP_OUT="$(mktemp)"
    if ! printf '%s\n' 'Return exactly: html-explainer-ok' | "${CODEX_EXEC_BIN:-codex}" exec --ephemeral --skip-git-repo-check --sandbox read-only --model "$DEFAULT_CODEX_MODEL" -c "model_reasoning_effort=\"$DEFAULT_EXPLAINER_THINKING\"" --output-last-message "$TMP_OUT" - >/dev/null 2>&1; then
      echo "error: codex exec explainer backend preflight failed; authenticate Codex or set HTML_EXPLAIN_SKIP_BACKEND_PREFLIGHT=1 for debugging" >&2
      exit 1
    fi
    if [[ "$(tr -d '\r\n ' < "$TMP_OUT")" != "html-explainer-ok" ]]; then
      echo "error: codex exec explainer backend preflight returned unexpected output" >&2
      exit 1
    fi
    rm -f "$TMP_OUT"
    echo "HTML explainer deep backend preflight OK: codex exec"
  fi
elif [[ "$DEEP_CHECK" == "1" ]]; then
  echo "HTML explainer deep backend preflight skipped by HTML_EXPLAIN_SKIP_BACKEND_PREFLIGHT=1"
fi

echo "HTML explainer preflight OK: server started at http://127.0.0.1:$PORT"
echo "HTML explainer question endpoint OK: /api/review-question"
echo "default explainer QA model: $DEFAULT_CODEX_MODEL"
echo "default explainer QA thinking level: $DEFAULT_EXPLAINER_THINKING"
