# Muse unified delivery

The user asks for research, not CLI operations. Muse should ingest the Evidence Pack, generate the canonical report, and (when explicitly requested) produce a podcast via Open Notebook. After the podcast job completes, run a **single delivery command**:

```bash
.venv/bin/focu deliver --evidence-id ev_REAL_ID --episode-id 'episode:REAL_ID' --output-dir data/deliveries/topic
```

If Open Notebook returns an episode ID in the completed job's result, you can use:

```bash
.venv/bin/focu deliver --evidence-id ev_REAL_ID --job-id 'job:REAL_ID' --output-dir data/deliveries/topic
```

The command writes `research.md`, `transcript.json` (when available), and `podcast.mp3`, while archiving text/metadata in Focu SQLite. Return both the reading and listening paths to the user. Do not expose implementation details unless asked.

**Important:** The Open Notebook job API may not return an episode ID. In that case the command fails with an actionable message: run `focu podcast episodes`, identify the exact episode, and retry with `--episode-id`. Never guess an episode ID or match by title alone. Failed/incomplete jobs are not archived as completed podcasts. A report may be archived first, even when audio is still pending. The transcript preserves what was spoken, including unsupported claims; the Markdown report remains canonical.

This command is idempotent for the same episode and evidence ID, but is not an unattended scheduler. It should be invoked by Muse at the end of the approved podcast generation workflow. It does not change or overwrite the original Open Notebook episode.
