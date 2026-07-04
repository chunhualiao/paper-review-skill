# Security Policy

## Supported Versions

Security fixes target the default branch until versioned releases are published.

## Reporting a Vulnerability

Report vulnerabilities through GitHub private vulnerability reporting when
available, or contact the repository maintainer directly before opening a public
issue.

Do not include private papers, confidential review content, model transcripts,
credentials, tokens, or local filesystem paths in public reports.

## Security Model

This project is designed for local, single-user paper review workflows. It can:

- run `codex exec` through local scripts,
- start localhost-only HTTP services for OCR and HTML explanation,
- forward review-page context to the configured model backend,
- read and write local review artifacts.

Treat papers and generated review pages as untrusted input. Do not expose the
local explainer server or OCR shim to untrusted networks.
