# TTS onboarding for external agents (experimental)

Focu does **not** have the ability to force a native Muse/OpenClaw popup. The host agent should inspect `focu tts status` after installation, ask the user whether to enable speech, and if the user agrees offer an interactive terminal or its own secure secret-entry UI.

```bash
.venv/bin/focu tts status
.venv/bin/focu tts setup
```

`setup` requires a real interactive terminal, requests explicit consent, uses hidden input, and writes the key to ignored `data/tts-config.json` with owner-only permissions. The alternative is to inject `OPENAI_API_KEY` through a host-managed secret store. **Never** paste API keys into chat, CLI arguments, source files, logs, or Git.

This initial provider adapter uses the OpenAI Speech API. No key is sent during setup; a provider request happens only during explicit synthesis. It is **not** a generic provider-selection UI. The `synthesize` command rejects scripts longer than 4,000 characters instead of silently truncating them. For longer scripts, `synthesize-long` chunks the text at paragraph/sentence boundaries (never mid-sentence when a boundary fits), synthesizes the chunks in order with the same voice and model, and concatenates them into one MP3 with chunk-boundary silences normalized to a ~0.7s gap; a failed chunk aborts the run and leaves no partial MP3. Audio QA (decode/duration) is the caller's post-audio audit — see `focu.media_integrity` and the daily pipeline's finalize stage.

```bash
.venv/bin/focu tts synthesize --input data/episodes/DATE/research-script.txt --output data/episodes/DATE/research.mp3
.venv/bin/focu tts synthesize-long --input data/episodes/DATE/research-script.txt --output data/episodes/DATE/research.mp3
```

Configuration note for hosts: synthesis needs a credential the adapter can reach (environment or the private config written by `focu tts setup`). On hosts where the owner's key is held behind a connector surrogate and is not reachable by local processes at all, do not force this adapter — configure the daily pipeline's `tts_argv` with the host helper command instead (same contract: script file in, MP3 out, voice parameter); see docs/PERSISTENT_PIPELINE.md.

The legacy `FOCU_TTS_CMD` shell-eval hook has been removed from the standard synthesize script to avoid executing arbitrary configured shell text. Use the provider adapter or implement an explicit vetted backend.
