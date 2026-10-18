# Open Notebook podcast integration — Muse acceptance test

Focu uses **Open Notebook as its podcast generation backend**. Focu remains the source of truth for user-defined sources, research evidence and intent. Muse/OpenClaw is the researcher. The Open Notebook adapter submits **explicit content** to the API; it does not grant Open Notebook permission to browse new sources or silently expand research scope.

## Prerequisites

1. Install Focu with `bash scripts/bootstrap.sh` (Python 3.10+).
2. Install and start a separate Open Notebook instance, including its **API and background worker**, following its official deployment instructions: https://github.com/lfnovo/open-notebook .
3. In Open Notebook, configure an LLM for outline/transcript generation and a TTS model/provider. Create or select an **Episode Profile** and **Speaker Profile**. Focu does not configure those provider credentials.
4. Set `OPEN_NOTEBOOK_URL` (default `http://127.0.0.1:5055`). If the server has password protection, set `OPEN_NOTEBOOK_PASSWORD` through the host's secure secret store or private terminal. **Do not paste secrets into chat or Git.** Do not expose an unauthenticated Open Notebook API publicly.

## Muse instructions: first live run

Read `SKILL.md` and `docs/AGENT_INSTALL.md`. Ask the user which already-approved evidence or content to turn into an episode. Do not fabricate research. A cited Markdown digest produced by `focu ingest-evidence` is an appropriate input. Confirm the user agrees to send its content to the configured Open Notebook instance.

```bash
.venv/bin/focu podcast doctor
```

Doctor checks API health and lists available profiles; it **does not** verify the background worker or paid provider credentials. If either profile list is empty, configure profiles in Open Notebook first. Choose the names returned by doctor, not assumed defaults.

```bash
.venv/bin/focu podcast generate \
  --content-file data/research/digest.md \
  --episode-name "My first Focu research briefing" \
  --episode-profile "NAME_FROM_DOCTOR" \
  --speaker-profile "NAME_FROM_DOCTOR"
```

This returns a **job ID**, not an MP3. Track progress and failures:

```bash
.venv/bin/focu podcast job "JOB_ID_FROM_GENERATE"
.venv/bin/focu podcast episodes
```

When the job reports completion, find the episode ID in `episodes` and download:

```bash
.venv/bin/focu podcast download "EPISODE_ID" --output data/episodes/first-focu.mp3
```

Review the generated script and audio against the original Evidence Pack. Podcast content can introduce unsupported statements even when its input was cited. Keep source URLs and uncertainty in the input; audio citations may be lost in speech. Record defects and user feedback before changing profiles.

## Failure diagnosis

- Connection refused: Open Notebook API not running, wrong `OPEN_NOTEBOOK_URL`, or unreachable host.
- HTTP 401: password not configured correctly.
- Empty profile lists: create profiles and configure models in Open Notebook.
- Job stuck queued: check Open Notebook background worker.
- Job failed: check Open Notebook worker logs and provider model/TTS configuration.
- Completed job without audio: inspect episode status and `audio_url`; retry after fixing the provider.

## Security and boundaries

The adapter uses Python's standard library, with no new Focu dependencies. It does not automatically deploy Open Notebook, configure LLM/TTS providers, schedule episodes, or publish a podcast feed. The existing `focu tts` feature is a separate short-form speech adapter; its OpenAI API key is **not** automatically reused by Open Notebook. Network calls occur only when podcast commands are explicitly invoked. The Open Notebook API may be remote: content sent to it leaves Focu's local storage.

API verified against Open Notebook's `api/routers/podcasts.py`, `api/podcast_service.py`, and published REST API reference as of October 2026. On newer versions, check `http://localhost:5055/openapi.json`.
