# v0.2.1 — Evidence auditability and fetch reliability

- Markdown now shows `evidence_quote` beneath its finding.
- Quote matching collapses whitespace (tabs/newlines/repeated spaces) before substring checking. It does not perform semantic verification.
- `the-few fetch URL --retries 2` retries timeouts, HTTP 429 and HTTP 5xx with bounded exponential delays; HTTP 403 and other 4xx are not retried.
- Fetch failures return JSON errors with `category` and `http_status` when available.
- `the-few fetch URL --snapshot-dir data/snapshots` writes a content-addressed UTF-8 text file and JSON metadata with URL, capture time and SHA256.
- `the-few verify-snapshot PATH SHA256` detects changed bytes (exit 1 on mismatch).
- Snapshots prove local content integrity, not source authenticity or claim correctness. An agent can still fabricate captured text.
- **Security:** the fetcher is not SSRF-hardened. Do not expose it to untrusted users or unrestricted server-side agent execution; enforce network egress controls.
- Live external tests are opt-in; the default CI uses deterministic fixtures.
