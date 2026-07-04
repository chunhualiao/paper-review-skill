#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WRAPPER="$ROOT/scripts/run_olmocr.sh"
OLMOCR_BIN="$ROOT/.venv-olmocr/bin/olmocr"
SHIM="$ROOT/scripts/codex_exec_openai_shim.py"
TIMING_SCRIPT="$ROOT/scripts/audit_timing.py"
DEFAULT_CODEX_MODEL="${PAPER_REVIEW_CODEX_MODEL:-${CODEX_EXEC_MODEL:-${CODEX_MODEL:-gpt-5.5}}}"
DEFAULT_PREFLIGHT_THINKING="${PAPER_REVIEW_THINKING_PREFLIGHT:-low}"

case "${1:-}" in
  -h|--help)
    cat <<EOF
Usage: scripts/check_olmocr_required.sh

Verify required OCR dependencies before using the research-paper-review skill.

Checks:
  - repo-local or PATH olmOCR command
  - default Codex-backed OCR shim
  - timing helper
  - authenticated codex exec path unless CODEX_OLMOCR_SKIP_CODEX_PREFLIGHT=1
EOF
    exit 0
    ;;
esac

if [[ -x "$OLMOCR_BIN" ]] && "$OLMOCR_BIN" --help >/dev/null 2>&1; then
  OLMOCR_OK="$OLMOCR_BIN --help"
elif [[ -x "$WRAPPER" ]] && OLMOCR_SERVER=explicit "$WRAPPER" --help >/dev/null 2>&1; then
  OLMOCR_OK="$WRAPPER --help"
elif command -v olmocr >/dev/null 2>&1 && olmocr --help >/dev/null 2>&1; then
  OLMOCR_OK="$(command -v olmocr) --help"
else
  cat >&2 <<'EOF'
error: olmOCR is mandatory before running the research-paper-review skill.

Install the repo-local OCR environment, then rerun this preflight:

  python3 -m venv .venv-olmocr
  .venv-olmocr/bin/python -m pip install --upgrade pip setuptools wheel
  .venv-olmocr/bin/python -m pip install olmocr
  scripts/check_olmocr_required.sh
EOF
  exit 1
fi

[[ -f "$SHIM" ]] || { echo "error: missing default codex-exec olmOCR shim: $SHIM" >&2; exit 1; }
python3 -m py_compile "$SHIM"
[[ -f "$TIMING_SCRIPT" ]] || { echo "error: missing timing audit helper: $TIMING_SCRIPT" >&2; exit 1; }
python3 -m py_compile "$TIMING_SCRIPT"

command -v "${CODEX_BIN:-codex}" >/dev/null 2>&1 || {
  cat >&2 <<'EOF'
error: codex CLI is required by default for paper-review-skill OCR.

Install and authenticate Codex with your OpenAI Pro/Plus subscription. This skill defaults to a single `codex exec` backend for OCR and review.
EOF
  exit 1
}

if [[ "${CODEX_OLMOCR_SKIP_CODEX_PREFLIGHT:-0}" != "1" ]]; then
  TMP_OUT="$(mktemp)"
  cleanup() { rm -f "$TMP_OUT"; }
  trap cleanup EXIT
  if ! printf '%s\n' 'Return exactly: codex-ok' | "${CODEX_BIN:-codex}" exec --ephemeral --skip-git-repo-check --sandbox read-only --model "$DEFAULT_CODEX_MODEL" -c "model_reasoning_effort=\"$DEFAULT_PREFLIGHT_THINKING\"" --output-last-message "$TMP_OUT" - >/dev/null 2>&1; then
    echo "error: codex exec preflight failed; authenticate Codex before using the default olmOCR backend" >&2
    exit 1
  fi
  if [[ "$(tr -d '\r\n ' < "$TMP_OUT")" != "codex-ok" ]]; then
    echo "error: codex exec preflight returned unexpected output" >&2
    exit 1
  fi
fi

echo "olmOCR preflight OK: $OLMOCR_OK"
echo "default olmOCR backend OK: codex-exec shim via ${CODEX_BIN:-codex}"
echo "default codex model: $DEFAULT_CODEX_MODEL"
echo "preflight thinking level: $DEFAULT_PREFLIGHT_THINKING"
echo "timing audit OK: $TIMING_SCRIPT"
