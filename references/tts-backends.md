# TTS backends (M1)

Audio mode requires ffmpeg/ffprobe plus an explicit TTS argv template:

```yaml
tts_argv:
  - /absolute/path/to/tts
  - --input
  - "{input}"
  - --output
  - "{output}"
  - --voice
  - "{voice}"
```

The backend must read UTF-8 Host:-labelled text and produce a non-empty MP3 at
the requested output path. Voice comes from the channel. The output is a temp
file in the episode directory and may already exist; the backend must overwrite
it. The timeout is 300 seconds; longer-running providers need a later async
adapter. Stderr/stdout are captured to keep machine JSON output parseable.

For old setups, THEFEW_TTS_CMD (preferred) or THEVIEW_TTS_CMD is parsed with
shlex into argv; literal $IN/$OUT placeholders are replaced. No eval, shell
expansion, pipelines or redirection occur. Example:

```bash
export THEFEW_TTS_CMD='my-tts --input "$IN" --output "$OUT"'
```

The command is trusted local configuration, never taken from collected text or
shared lists. Credentials belong in environment variables. Runtime command
repair does not invalidate frozen content.

No backend is not a successful audio episode. Choose output_mode: text_only or
--text-only explicitly for text completion. Failed TTS preserves the script and
selection and leaves coverage absent. Per-channel results report failure; CLI
run/synthesize exits 4 when any required episode fails.

MP3 checks verify format, positive duration and decoding. They do not verify
speech completeness, language, or whether a person heard it. A receipt keyed
by episode/script/audio hashes enables crash recovery without repeated TTS.
