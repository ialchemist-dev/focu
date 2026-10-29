# TTS onboarding for external agents (experimental)

Focu does **not** have the ability to force a native Muse/OpenClaw popup. The host agent should inspect `focu tts status` after installation, ask the user whether to enable speech, and if the user agrees offer an interactive terminal or its own secure secret-entry UI.

```bash
.venv/bin/focu tts status
.venv/bin/focu tts setup
```

`setup` requires a real interactive terminal, requests explicit consent, uses hidden input, and writes the key to ignored `data/tts-config.json` with owner-only permissions. The alternative is to inject `OPENAI_API_KEY` through a host-managed secret store. **Never** paste API keys into chat, CLI arguments, source files, logs, or Git.

This initial provider adapter uses the OpenAI Speech API. No key is sent during setup; a provider request happens only during explicit synthesis. It is **not** a generic provider-selection UI. The current implementation rejects scripts longer than 4,000 characters instead of silently truncating them; long-form chunking and audio QA remain to be implemented.

```bash
.venv/bin/focu tts synthesize --input data/episodes/DATE/research-script.txt --output data/episodes/DATE/research.mp3
```

The legacy `FOCU_TTS_CMD` shell-eval hook has been removed from the standard synthesize script to avoid executing arbitrary configured shell text. Use the provider adapter or implement an explicit vetted backend.
