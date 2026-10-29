# Agent installation and usage (Muse, OpenClaw, other agents)

## Objective and honest boundary

This repository is a **portable, installable research handoff tool**, not a self-running research agent. The host agent (Muse/OpenClaw/etc.) must perform retrieval, evaluate evidence, and write the Evidence Pack. Focu validates source references, persists research and renders cited Markdown. No model credentials are required for this handoff.

## Prerequisites

- Git and Python 3.10+ with `venv` and pip
- Network for initial installation and optional real webpage retrieval
- Write permission in the checkout directory

## Bootstrap

```bash
git clone https://github.com/ialchemist-dev/the-few.git focu
cd focu
bash scripts/bootstrap.sh
.venv/bin/focu doctor
```

Bootstrap installs the minimal Python package in a local virtual environment, initializes SQLite under `data/`, and prints a health summary. No credentials are written or requested. For the older scheduled podcast pipeline, install optional dependencies with `.venv/bin/python -m pip install -e '.[daily]'`.

## Agent execution protocol

Use the CLI (all results JSON except Markdown artifact):

```bash
.venv/bin/focu capture "Why do tools constrain us?"
.venv/bin/focu list --status queued
.venv/bin/focu start <intent_id>
.venv/bin/focu fetch https://docs.python.org/3/
```

The agent must research the question using approved sources, inspect the actual content, and produce a JSON object with the fields defined in `schemas/evidence-pack.schema.json`. The following is a **shape-only legacy-compatible example**, not verified research. Missing provenance fields do not establish that a claim has been checked. For evidence-backed handoff, include `source_type`, `access_status`, `verification`, `original_source_accessed`, and `extracted_text` on each source, plus a verbatim `evidence_quote` on each finding. See `docs/EVIDENCE_PROVENANCE.md`. Example:

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

Write it to an ignored local path, for example `data/research/evidence.json`. Replace the sample claim with one genuinely supported by the source. **Do not treat this example as verified evidence:** legacy packs are accepted for compatibility but their claims lack provenance checks. A fully verified pack must contain genuine extracted source text and matching quotations.

```bash
.venv/bin/focu ingest-evidence --evidence data/research/evidence.json --output data/research/digest.md
.venv/bin/focu show <intent_id>
.venv/bin/focu show-evidence ev_example
```

If research fails, run `.venv/bin/focu fail <intent_id> --error "reason"`; retry later with `retry`. Never mark research complete if the sources cannot be verified. Do not silently convert one-time questions into subscriptions.

## Verification

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest discover -s tests/unit -v
FOCU_LIVE_TESTS=1 .venv/bin/python -m unittest discover -s tests/integration -v
```

Live tests use the public internet and are opt-in. Research quality still requires source-by-source review. See `docs/testing.md`.

## Security and current limitations

- `focu fetch` accepts arbitrary HTTP(S) URLs, including potentially private network addresses. **Do not expose this CLI as an unrestricted remote endpoint**; sandbox outbound access and implement SSRF protections before production deployment.
- Only public HTML and plain text extraction are supported; PDF and JS-rendered sites are not.
- No automatic source discovery, research orchestration, digest scheduler, neural TTS, or Muse-specific plugin installation API is implemented.
- The skill file is an agent-readable contract, not proof that Muse automatically discovers it. Muse must be able to read this checkout and invoke shell commands; verify this on the actual Muse runtime.
- Personal SQLite databases, evidence, output and credentials must remain local and out of Git.

## Podcast generation with Open Notebook

For the first Muse end-to-end podcast run, see `docs/OPEN_NOTEBOOK_MUSE_TEST.md`. Install/start Open Notebook separately, configure its models and profiles, then use `.venv/bin/focu podcast doctor/generate/job/episodes/download`. No TTS API key is required by Focu's adapter itself; the Open Notebook server manages its own provider credentials.
