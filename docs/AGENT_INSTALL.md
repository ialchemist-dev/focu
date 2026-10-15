# Agent installation and usage (Muse, OpenClaw, other agents)

## Objective and honest boundary

This repository is a **portable, installable research handoff tool**, not a self-running research agent. The host agent (Muse/OpenClaw/etc.) must perform retrieval, evaluate evidence, and write the Evidence Pack. The Few validates source references, persists research and renders cited Markdown. No model credentials are required for this handoff.

## Prerequisites

- Git and Python 3.10+ with `venv` and pip
- Network for initial installation and optional real webpage retrieval
- Write permission in the checkout directory

## Bootstrap

```bash
git clone https://github.com/ialchemist-dev/the-few.git
cd the-few
# Remove this checkout once PR #2 is merged:
git checkout feat/v0.2-intent-contracts
bash scripts/bootstrap.sh
.venv/bin/the-few doctor
```

Bootstrap installs the minimal Python package in a local virtual environment, initializes SQLite under `data/`, and prints a health summary. No credentials are written or requested. For the older scheduled podcast pipeline, install optional dependencies with `.venv/bin/python -m pip install -e '.[daily]'`.

## Agent execution protocol

Use the CLI (all results JSON except Markdown artifact):

```bash
.venv/bin/the-few capture "Why do tools constrain us?"
.venv/bin/the-few list --status queued
.venv/bin/the-few start <intent_id>
.venv/bin/the-few fetch https://docs.python.org/3/
```

The agent must research the question using approved sources, inspect the actual content, and produce a JSON object with the fields defined in `schemas/evidence-pack.schema.json`. Example:

```json
{
  "schema_version": "0.2",
  "id": "ev_example",
  "intent_id": "REPLACE_WITH_REAL_INTENT_ID",
  "summary": "Concise research summary supported by the evidence below.",
  "findings": [
    {
      "claim": "A claim supported by the cited page.",
      "source_ids": ["s1"],
      "uncertainty": "What remains unclear"
    }
  ],
  "sources": [
    {"id": "s1", "url": "https://docs.python.org/3/", "title": "Python Documentation"}
  ],
  "created_at": "2026-10-15T00:00:00Z"
}
```

Write it to an ignored local path, for example `data/research/evidence.json`. Replace the sample claim with one genuinely supported by the source; this JSON is a shape example, **not** a valid researched result.

```bash
.venv/bin/the-few ingest-evidence --evidence data/research/evidence.json --output data/research/digest.md
.venv/bin/the-few show <intent_id>
.venv/bin/the-few show-evidence ev_example
```

If research fails, run `.venv/bin/the-few fail <intent_id> --error "reason"`; retry later with `retry`. Never mark research complete if the sources cannot be verified. Do not silently convert one-time questions into subscriptions.

## Verification

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest discover -s tests/unit -v
THE_FEW_LIVE_TESTS=1 .venv/bin/python -m unittest discover -s tests/integration -v
```

Live tests use the public internet and are opt-in. Research quality still requires source-by-source review. See `docs/testing.md`.

## Security and current limitations

- `the-few fetch` accepts arbitrary HTTP(S) URLs, including potentially private network addresses. **Do not expose this CLI as an unrestricted remote endpoint**; sandbox outbound access and implement SSRF protections before production deployment.
- Only public HTML and plain text extraction are supported; PDF and JS-rendered sites are not.
- No automatic source discovery, research orchestration, digest scheduler, neural TTS, or Muse-specific plugin installation API is implemented.
- The skill file is an agent-readable contract, not proof that Muse automatically discovers it. Muse must be able to read this checkout and invoke shell commands; verify this on the actual Muse runtime.
- Personal SQLite databases, evidence, output and credentials must remain local and out of Git.
