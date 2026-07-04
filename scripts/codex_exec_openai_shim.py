#!/usr/bin/env python3
"""OpenAI-compatible olmOCR shim backed by authenticated `codex exec`."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import BoundedSemaphore, Lock
from typing import Any

from model_policy import model as default_model
from model_policy import thinking_level


CODEX_MODEL = os.environ.get("CODEX_EXEC_MODEL") or default_model()
MODEL_ID = os.environ.get("CODEX_OLMOCR_SHIM_MODEL", CODEX_MODEL)
CODEX_BIN = os.environ.get("CODEX_BIN", "codex")
CODEX_REASONING_EFFORT = os.environ.get("CODEX_EXEC_REASONING_EFFORT") or thinking_level("ocr")
CODEX_TIMEOUT_SEC = int(os.environ.get("CODEX_EXEC_TIMEOUT_SEC", "240"))
MAX_CONCURRENT = int(os.environ.get("CODEX_OLMOCR_SHIM_MAX_CONCURRENT", "1"))
API_KEY = os.environ.get("CODEX_OLMOCR_SHIM_API_KEY")
TIMING_LOG = os.environ.get("CODEX_OLMOCR_TIMING_LOG")

REQUEST_LIMIT = BoundedSemaphore(MAX_CONCURRENT)
REQUEST_INDEX_LOCK = Lock()
REQUEST_INDEX = 0


def next_request_index() -> int:
    global REQUEST_INDEX
    with REQUEST_INDEX_LOCK:
        REQUEST_INDEX += 1
        return REQUEST_INDEX


def iso_from_epoch(seconds: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))


def append_timing(entry: dict[str, Any]) -> None:
    if not TIMING_LOG:
        return
    path = Path(TIMING_LOG).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def page_number_guess(prompt: str) -> int | None:
    match = re.search(r"\bpage\s+(?:number\s+)?(\d{1,5})\b", prompt, flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def error(handler: BaseHTTPRequestHandler, status: int, message: str) -> None:
    json_response(handler, status, {"error": {"message": message, "type": "codex_exec_shim_error"}})


def authorized(handler: BaseHTTPRequestHandler) -> bool:
    if not API_KEY:
        return True
    return handler.headers.get("Authorization") == f"Bearer {API_KEY}"


def extract_request(payload: dict[str, Any], tmpdir: Path) -> tuple[str, list[str]]:
    prompt_parts = [
        "You are a compatibility backend for an OCR pipeline.",
        "Follow the OCR request exactly and return only the requested document text or Markdown.",
        "Do not explain, summarize, review, or mention Codex.",
        "",
    ]
    image_paths: list[str] = []

    for message in payload.get("messages", []):
        content = message.get("content", "")
        if isinstance(content, str):
            prompt_parts.append(content)
            continue
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                prompt_parts.append(str(part.get("text", "")))
            elif part.get("type") == "image_url":
                image_url = part.get("image_url", {}).get("url", "")
                if image_url.startswith("data:image/") and ";base64," in image_url:
                    header, encoded = image_url.split(";base64,", 1)
                    suffix = ".jpg" if "jpeg" in header or "jpg" in header else ".png"
                    image_path = tmpdir / f"page-{len(image_paths) + 1}{suffix}"
                    image_path.write_bytes(base64.b64decode(encoded))
                    image_paths.append(str(image_path))

    return "\n".join(prompt_parts).strip() + "\n", image_paths


def run_codex(prompt: str, image_paths: list[str]) -> str:
    with tempfile.TemporaryDirectory(prefix="codex-olmocr-response-") as response_dir:
        output_path = Path(response_dir) / "final.txt"
        command = [
            CODEX_BIN,
            "exec",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "-c",
            f'model_reasoning_effort="{CODEX_REASONING_EFFORT}"',
            "--output-last-message",
            str(output_path),
        ]
        if CODEX_MODEL:
            command.extend(["--model", CODEX_MODEL])
        for image_path in image_paths:
            command.extend(["-i", image_path])
        command.append("-")

        result = subprocess.run(
            command,
            input=prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=CODEX_TIMEOUT_SEC,
            check=False,
        )
        if result.returncode != 0:
            stderr_tail = result.stderr[-2000:] if result.stderr else ""
            stdout_tail = result.stdout[-2000:] if result.stdout else ""
            raise RuntimeError(f"codex exec failed with code {result.returncode}\n{stderr_tail}\n{stdout_tail}")
        if not output_path.exists():
            raise RuntimeError("codex exec completed without writing the final message")
        return output_path.read_text(encoding="utf-8").strip()


class ShimHandler(BaseHTTPRequestHandler):
    server_version = "codex-olmocr-shim/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}", flush=True)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") not in {"/v1/models", "/models"}:
            error(self, 404, f"unknown endpoint: {self.path}")
            return
        json_response(
            self,
            200,
            {
                "object": "list",
                "data": [{"id": MODEL_ID, "object": "model", "created": int(time.time()), "owned_by": "codex-exec-shim"}],
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") not in {"/v1/chat/completions", "/chat/completions"}:
            error(self, 404, f"unknown endpoint: {self.path}")
            return
        if not authorized(self):
            error(self, 401, "invalid shim API key")
            return

        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as exc:
            error(self, 400, f"invalid JSON: {exc}")
            return

        if not REQUEST_LIMIT.acquire(timeout=1):
            error(self, 429, "codex exec shim is busy; run olmOCR with max_concurrent_requests=1")
            return

        request_index = next_request_index()
        started_epoch = time.time()
        started_monotonic = time.monotonic()
        status = "completed"
        error_message = ""
        image_count = 0
        output_chars = 0
        page_guess: int | None = None

        def record_timing() -> None:
            ended_epoch = time.time()
            duration = time.monotonic() - started_monotonic
            metadata: dict[str, Any] = {
                "backend": "codex-exec-shim",
                "model": payload.get("model") or MODEL_ID,
                "codex_model": CODEX_MODEL,
                "thinking_level": CODEX_REASONING_EFFORT,
                "page_request_index": request_index,
                "page_number_guess": page_guess,
                "image_count": image_count,
                "output_chars": output_chars,
            }
            if error_message:
                metadata["error"] = error_message[:1000]
            append_timing(
                {
                    "schema": "paper-review-timing/v1",
                    "kind": "olmocr_page",
                    "step": "olmocr.page",
                    "category": "ocr_page",
                    "status": status,
                    "started_at": iso_from_epoch(started_epoch),
                    "ended_at": iso_from_epoch(ended_epoch),
                    "started_epoch_ms": int(started_epoch * 1000),
                    "ended_epoch_ms": int(ended_epoch * 1000),
                    "duration_ms": int(duration * 1000),
                    "metadata": metadata,
                }
            )

        try:
            with tempfile.TemporaryDirectory(prefix="codex-olmocr-request-") as tmp:
                prompt, image_paths = extract_request(payload, Path(tmp))
                image_count = len(image_paths)
                page_guess = page_number_guess(prompt)
                content = run_codex(prompt, image_paths)
                output_chars = len(content)
        except subprocess.TimeoutExpired:
            status = "timeout"
            error_message = f"codex exec exceeded CODEX_EXEC_TIMEOUT_SEC={CODEX_TIMEOUT_SEC}"
            record_timing()
            error(self, 504, f"codex exec exceeded CODEX_EXEC_TIMEOUT_SEC={CODEX_TIMEOUT_SEC}")
            return
        except Exception as exc:
            status = "failed"
            error_message = str(exc)
            record_timing()
            error(self, 500, str(exc))
            return
        finally:
            REQUEST_LIMIT.release()

        record_timing()
        print(
            f"completed olmOCR page request {request_index} in {time.time() - started_epoch:.1f}s, {len(content)} output chars",
            flush=True,
        )
        json_response(
            self,
            200,
            {
                "id": f"chatcmpl-codex-shim-{uuid.uuid4().hex}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": payload.get("model") or MODEL_ID,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenAI-compatible local server backed by codex exec.")
    parser.add_argument("--host", default=os.environ.get("CODEX_OLMOCR_SHIM_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("CODEX_OLMOCR_SHIM_PORT", "57891")))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), ShimHandler)
    print(f"codex exec olmOCR shim listening at http://{args.host}:{args.port}/v1", flush=True)
    print(f"model: {MODEL_ID}; codex reasoning effort: {CODEX_REASONING_EFFORT}; max concurrent: {MAX_CONCURRENT}", flush=True)
    if TIMING_LOG:
        print(f"page timing log: {TIMING_LOG}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
