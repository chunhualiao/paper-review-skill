#!/usr/bin/env python3
"""Download a paper URL into an auditable local PDF artifact."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.message import Message
from pathlib import Path


USER_AGENT = "paper-review-skill/1.0 (+https://github.com/chunhualiao/paper-review-skill)"
MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024
MIN_PDF_BYTES = 8


class FetchPaperError(RuntimeError):
    """Raised when a paper URL cannot be safely turned into a PDF."""


@dataclass(frozen=True)
class FetchResult:
    paper_id: str
    pdf_path: Path
    metadata_path: Path
    metadata: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "paper_id": self.paper_id,
            "pdf_path": str(self.pdf_path),
            "metadata_path": str(self.metadata_path),
            "metadata": self.metadata,
        }


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sanitize_paper_id(value: str) -> str:
    cleaned = Path(value).name
    cleaned = re.sub(r"\.pdf$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", cleaned)
    cleaned = cleaned.strip(".-_")
    return cleaned[:120] or "paper"


def resolve_paper_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path
    if host in {"arxiv.org", "www.arxiv.org"}:
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 2 and parts[0] in {"abs", "pdf"}:
            paper_id = parts[1]
            if paper_id.endswith(".pdf"):
                paper_id = paper_id[:-4]
            return f"https://arxiv.org/pdf/{paper_id}.pdf"
    return url


def paper_id_from_url(url: str) -> str:
    resolved = resolve_paper_url(url)
    parsed = urllib.parse.urlparse(resolved)
    name = Path(urllib.parse.unquote(parsed.path)).name
    if name:
        return sanitize_paper_id(name)
    host = parsed.netloc.split(":")[0]
    return sanitize_paper_id(host or "paper")


def filename_from_headers(headers: Message) -> str | None:
    disposition = headers.get("Content-Disposition")
    if not disposition:
        return None
    params = {}
    for item in urllib.request.parse_http_list(disposition):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        params[key.strip().lower()] = value.strip().strip('"')
    filename = params.get("filename")
    return sanitize_paper_id(filename) + ".pdf" if filename else None


def is_probably_pdf(data: bytes, content_type: str, final_url: str) -> bool:
    has_pdf_magic = data.lstrip().startswith(b"%PDF-")
    content_type = content_type.lower().split(";", 1)[0].strip()
    if content_type == "application/pdf":
        return has_pdf_magic
    if final_url.lower().endswith(".pdf") or content_type in {"application/octet-stream", "binary/octet-stream"}:
        return has_pdf_magic
    return False


def read_response_limited(response) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_DOWNLOAD_BYTES:
            raise FetchPaperError(f"download exceeded {MAX_DOWNLOAD_BYTES} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def failure_metadata(
    *,
    original_url: str,
    requested_url: str,
    artifact_root: Path,
    paper_id: str,
    message: str,
) -> Path:
    path = artifact_root / paper_id / "source" / "download_failure.json"
    write_json(
        path,
        {
            "status": "failed",
            "paper_id": paper_id,
            "original_url": original_url,
            "requested_url": requested_url,
            "error": message,
            "downloaded_at": utc_now_iso(),
        },
    )
    return path


def fetch_paper(url: str, *, artifact_root: Path, paper_id: str | None = None, timeout: float = 30.0) -> FetchResult:
    original_url = url
    requested_url = resolve_paper_url(url)
    safe_paper_id = sanitize_paper_id(paper_id) if paper_id else paper_id_from_url(requested_url)
    source_dir = artifact_root / safe_paper_id / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    request = urllib.request.Request(requested_url, headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = read_response_limited(response)
            final_url = response.geturl()
            status_code = int(response.status)
            headers = response.headers
    except (urllib.error.URLError, TimeoutError, OSError, FetchPaperError) as exc:
        failure_metadata(
            original_url=original_url,
            requested_url=requested_url,
            artifact_root=artifact_root,
            paper_id=safe_paper_id,
            message=str(exc),
        )
        raise FetchPaperError(f"failed to download paper URL: {exc}") from exc

    content_type = headers.get("Content-Type", "")
    if len(data) < MIN_PDF_BYTES or not is_probably_pdf(data, content_type, final_url):
        message = f"downloaded content is not a PDF: content_type={content_type or 'unknown'} final_url={final_url}"
        failure_metadata(
            original_url=original_url,
            requested_url=requested_url,
            artifact_root=artifact_root,
            paper_id=safe_paper_id,
            message=message,
        )
        raise FetchPaperError(message)

    header_filename = filename_from_headers(headers)
    if header_filename:
        pdf_name = header_filename
    else:
        pdf_name = f"{safe_paper_id}.pdf"
    pdf_name = sanitize_paper_id(pdf_name) + ".pdf"
    pdf_path = source_dir / pdf_name
    pdf_path.write_bytes(data)

    metadata_path = pdf_path.with_suffix(".download.json")
    metadata: dict[str, object] = {
        "status": "downloaded",
        "paper_id": safe_paper_id,
        "original_url": original_url,
        "requested_url": requested_url,
        "final_url": final_url,
        "http_status": status_code,
        "content_type": content_type,
        "content_length_header": headers.get("Content-Length"),
        "content_disposition": headers.get("Content-Disposition"),
        "byte_size": len(data),
        "sha256": sha256_bytes(data),
        "downloaded_at": utc_now_iso(),
        "pdf_path": str(pdf_path),
        "metadata_path": str(metadata_path),
    }
    write_json(metadata_path, metadata)
    return FetchResult(safe_paper_id, pdf_path, metadata_path, metadata)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download a paper URL into review_artifacts/<paper_id>/source/.")
    parser.add_argument("url", help="Paper URL. Direct PDF and arXiv abs/pdf URLs are supported.")
    parser.add_argument("--paper-id", help="Optional paper id override.")
    parser.add_argument("--artifact-root", default="review_artifacts", help="Artifact root. Default: review_artifacts.")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds. Default: 30.")
    parser.add_argument("--output-json", help="Optional path for a JSON summary of the downloaded paper.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = fetch_paper(
            args.url,
            artifact_root=Path(args.artifact_root),
            paper_id=args.paper_id,
            timeout=args.timeout,
        )
    except FetchPaperError as exc:
        print(f"fetch_paper.py: {exc}", file=sys.stderr)
        return 1

    payload = result.as_dict()
    if args.output_json:
        write_json(Path(args.output_json), payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
