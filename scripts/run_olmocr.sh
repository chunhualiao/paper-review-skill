#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OLMOCR_BIN="${OLMOCR_BIN:-$ROOT/.venv-olmocr/bin/olmocr}"
SHIM="$ROOT/scripts/codex_exec_openai_shim.py"
TIMING_SCRIPT="$ROOT/scripts/audit_timing.py"
MARKDOWN_NORMALIZER="$ROOT/scripts/normalize_olmocr_markdown.py"
DEFAULT_CODEX_MODEL="${PAPER_REVIEW_CODEX_MODEL:-${CODEX_EXEC_MODEL:-${CODEX_MODEL:-gpt-5.5}}}"
DEFAULT_OCR_THINKING="${PAPER_REVIEW_THINKING_OCR:-${CODEX_EXEC_REASONING_EFFORT:-low}}"
export CODEX_EXEC_MODEL="${CODEX_EXEC_MODEL:-$DEFAULT_CODEX_MODEL}"
export CODEX_EXEC_REASONING_EFFORT="${CODEX_EXEC_REASONING_EFFORT:-$DEFAULT_OCR_THINKING}"

has_arg() {
  local needle="$1"
  shift
  local arg
  for arg in "$@"; do
    [[ "$arg" == "$needle" || "$arg" == "$needle="* ]] && return 0
  done
  return 1
}

if has_arg "--help" "$@" || has_arg "-h" "$@"; then
  cat <<EOF
Usage: scripts/run_olmocr.sh <workspace> --pdfs <paper.pdf> [olmOCR options]

Run olmOCR through the paper-review policy wrapper.

Defaults:
  - Adds --markdown unless an output mode is already provided.
  - Uses the Codex-backed local shim when OLMOCR_SERVER is not set.
  - Writes timing logs when <workspace> is review_artifacts/<paper_id>/olmocr-workspace.
  - Normalizes Markdown to review_artifacts/<paper_id>/ocr/<paper_id>_olmocr.md.

Environment overrides:
  OLMOCR_BIN, OLMOCR_SERVER, OLMOCR_API_KEY, OLMOCR_MODEL
  PAPER_REVIEW_CODEX_MODEL, PAPER_REVIEW_THINKING_OCR
  PAPER_REVIEW_ARTIFACT_ROOT
EOF
  exit 0
fi

if [[ ! -x "$OLMOCR_BIN" ]]; then
  cat >&2 <<EOF
error: olmOCR is not installed at $OLMOCR_BIN

Install it with:
  cd "$ROOT"
  python3 -m venv .venv-olmocr
  .venv-olmocr/bin/python -m pip install --upgrade pip setuptools wheel
  .venv-olmocr/bin/python -m pip install olmocr
EOF
  exit 1
fi

DEFAULT_OUTPUT_ARGS=()
if ! has_arg "--markdown" "$@" && ! has_arg "--stats" "$@"; then
  DEFAULT_OUTPUT_ARGS+=(--markdown)
fi

WORKSPACE_ARG="${1:-}"
ARTIFACT_ROOT="${PAPER_REVIEW_ARTIFACT_ROOT:-}"
if [[ -z "$ARTIFACT_ROOT" && -n "$WORKSPACE_ARG" && "$WORKSPACE_ARG" != -* ]]; then
  workspace_base="$(basename "$WORKSPACE_ARG")"
  if [[ "$workspace_base" == "olmocr-workspace" || "$workspace_base" == "olmocr_workspace" ]]; then
    artifact_candidate="$(dirname "$WORKSPACE_ARG")"
    mkdir -p "$artifact_candidate/timing"
    ARTIFACT_ROOT="$(cd "$artifact_candidate" && pwd)"
  fi
fi

if [[ -n "$ARTIFACT_ROOT" ]]; then
  mkdir -p "$ARTIFACT_ROOT/timing"
  export PAPER_REVIEW_TIMING_LOG="${PAPER_REVIEW_TIMING_LOG:-$ARTIFACT_ROOT/timing/timing.jsonl}"
  export CODEX_OLMOCR_TIMING_LOG="${CODEX_OLMOCR_TIMING_LOG:-$ARTIFACT_ROOT/timing/olmocr-pages.jsonl}"
fi

now_ms() {
  if [[ -f "$TIMING_SCRIPT" ]]; then
    python3 "$TIMING_SCRIPT" now-ms
  else
    python3 - <<'PY'
import time
print(time.time_ns() // 1_000_000)
PY
  fi
}

record_olmocr_total() {
  local status="$1"
  local started_ms="$2"
  local ended_ms="$3"
  local backend="${OLMOCR_BACKEND_LABEL:-codex-exec-shim}"
  if [[ -n "${PAPER_REVIEW_TIMING_LOG:-}" && -f "$TIMING_SCRIPT" ]]; then
    python3 "$TIMING_SCRIPT" record \
      --log "$PAPER_REVIEW_TIMING_LOG" \
      --step "olmocr.total" \
      --category "ocr" \
      --status "$status" \
      --started-ms "$started_ms" \
      --ended-ms "$ended_ms" \
      --metadata "backend=$backend" \
      --metadata "model=${CODEX_EXEC_MODEL:-$DEFAULT_CODEX_MODEL}" \
      --metadata "thinking_level=${CODEX_EXEC_REASONING_EFFORT:-$DEFAULT_OCR_THINKING}" \
      --metadata "workspace=${WORKSPACE_ARG:-}" >/dev/null || true
  fi
}

summarize_timing() {
  if [[ -n "$ARTIFACT_ROOT" && -f "$TIMING_SCRIPT" ]]; then
    python3 "$TIMING_SCRIPT" summarize --artifact-root "$ARTIFACT_ROOT" >/dev/null || true
  fi
}

finalize_markdown_output() {
  [[ "${#DEFAULT_OUTPUT_ARGS[@]}" -gt 0 || " $* " == *" --markdown "* ]] || return 0
  [[ -n "$ARTIFACT_ROOT" ]] || return 0
  [[ -n "$WORKSPACE_ARG" && "$WORKSPACE_ARG" != -* ]] || return 0
  [[ -d "$WORKSPACE_ARG/markdown" ]] || {
    echo "error: olmOCR completed but no Markdown output was found under $WORKSPACE_ARG/markdown" >&2
    return 1
  }

  local found
  found="$(find "$WORKSPACE_ARG/markdown" -type f -name '*.md' 2>/dev/null | sort | head -1 || true)"
  if [[ -z "$found" ]]; then
    echo "error: olmOCR completed but no Markdown output was found under $WORKSPACE_ARG/markdown" >&2
    return 1
  fi

  local paper_id
  local output_dir
  local output_md
  paper_id="$(basename "$ARTIFACT_ROOT")"
  output_dir="$ARTIFACT_ROOT/ocr"
  output_md="$output_dir/${paper_id}_olmocr.md"
  mkdir -p "$output_dir"

  if [[ -f "$MARKDOWN_NORMALIZER" ]]; then
    python3 "$MARKDOWN_NORMALIZER" --input "$found" --output "$output_md" --source-label "$found" >/dev/null
  else
    cp "$found" "$output_md"
  fi
  echo "canonical single-column olmOCR Markdown: $output_md"
}

run_olmocr_with_timing() {
  local started_ms
  local ended_ms
  local status
  local exit_code
  started_ms="$(now_ms)"
  set +e
  "$OLMOCR_BIN" "$@"
  exit_code="$?"
  set -e
  if [[ "$exit_code" -eq 0 ]]; then
    status="completed"
    if ! finalize_markdown_output "$@"; then
      exit_code=1
      status="failed"
    fi
  else
    status="failed"
  fi
  ended_ms="$(now_ms)"
  record_olmocr_total "$status" "$started_ms" "$ended_ms"
  summarize_timing
  return "$exit_code"
}

if has_arg "--server" "$@"; then
  OLMOCR_BACKEND_LABEL="external-server"
  run_olmocr_with_timing "$@" ${DEFAULT_OUTPUT_ARGS+"${DEFAULT_OUTPUT_ARGS[@]}"}
  exit "$?"
fi

if [[ -n "${OLMOCR_SERVER:-}" ]]; then
  OLMOCR_BACKEND_LABEL="external-server"
  extra=()
  has_arg "--server" "$@" || extra+=(--server "$OLMOCR_SERVER")
  if [[ -n "${OLMOCR_API_KEY:-}" ]]; then
    has_arg "--api_key" "$@" || extra+=(--api_key "$OLMOCR_API_KEY")
  fi
  if [[ -n "${OLMOCR_MODEL:-}" ]]; then
    has_arg "--model" "$@" || extra+=(--model "$OLMOCR_MODEL")
  fi
  run_olmocr_with_timing "$@" ${DEFAULT_OUTPUT_ARGS+"${DEFAULT_OUTPUT_ARGS[@]}"} "${extra[@]}"
  exit "$?"
fi

command -v "${CODEX_BIN:-codex}" >/dev/null 2>&1 || {
  cat >&2 <<'EOF'
error: codex CLI is required by default for paper-review-skill OCR.

Install and authenticate Codex with your OpenAI Pro/Plus subscription, then verify:
  codex --version
  codex exec --skip-git-repo-check "Return exactly: ok"

To use a non-Codex olmOCR backend instead, set OLMOCR_SERVER and pass --server/--api_key/--model explicitly.
EOF
  exit 1
}

[[ -f "$SHIM" ]] || { echo "error: missing codex exec shim: $SHIM" >&2; exit 1; }

HOST="${CODEX_OLMOCR_SHIM_HOST:-127.0.0.1}"
if [[ -n "${CODEX_OLMOCR_SHIM_PORT:-}" ]]; then
  PORT="$CODEX_OLMOCR_SHIM_PORT"
else
  PORT="$(python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
)"
fi

if [[ -n "${CODEX_OLMOCR_SHIM_LOG:-}" ]]; then
  LOG="$CODEX_OLMOCR_SHIM_LOG"
elif [[ -n "$ARTIFACT_ROOT" ]]; then
  LOG="$ARTIFACT_ROOT/olmocr-shim.log"
else
  LOG="${TMPDIR:-/tmp}/codex-olmocr-shim-$$.log"
fi
python3 "$SHIM" --host "$HOST" --port "$PORT" >"$LOG" 2>&1 &
SHIM_PID="$!"
cleanup() {
  kill "$SHIM_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT

python3 - "$HOST" "$PORT" <<'PY'
import sys
import time
import urllib.request

host, port = sys.argv[1], sys.argv[2]
url = f"http://{host}:{port}/v1/models"
last = None
for _ in range(60):
    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            if response.status == 200:
                raise SystemExit(0)
    except Exception as exc:
        last = exc
    time.sleep(0.25)
raise SystemExit(f"codex-exec olmOCR shim did not become ready at {url}: {last}")
PY

extra=()
has_arg "--server" "$@" || extra+=(--server "http://$HOST:$PORT/v1")
has_arg "--api_key" "$@" || extra+=(--api_key "${CODEX_OLMOCR_SHIM_API_KEY:-codex-local}")
has_arg "--model" "$@" || extra+=(--model "${CODEX_OLMOCR_SHIM_MODEL:-$DEFAULT_CODEX_MODEL}")
has_arg "--pages_per_group" "$@" || extra+=(--pages_per_group "${OLMOCR_PAGES_PER_GROUP:-1}")
has_arg "--workers" "$@" || extra+=(--workers "${OLMOCR_WORKERS:-1}")
has_arg "--max_concurrent_requests" "$@" || extra+=(--max_concurrent_requests "${OLMOCR_MAX_CONCURRENT_REQUESTS:-1}")
if [[ -n "$ARTIFACT_ROOT" ]]; then
  has_arg "--disk_logging" "$@" || extra+=(--disk_logging "$ARTIFACT_ROOT/olmocr-run.log")
fi

run_olmocr_with_timing "$@" ${DEFAULT_OUTPUT_ARGS+"${DEFAULT_OUTPUT_ARGS[@]}"} "${extra[@]}"
