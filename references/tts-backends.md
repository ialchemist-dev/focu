# TTS backends

`synthesize.sh` delegates to whatever you set as `FOCU_TTS_CMD` —
a command where `$IN` is the script text file and `$OUT` is the MP3
to produce:

```bash
export FOCU_TTS_CMD='my-tts --input "$IN" --output "$OUT" --voice xiaobei'
./scripts/run-daily.sh
```

Without `FOCU_TTS_CMD`, synthesis is skipped and the script is
kept — the pipeline still delivers text episodes.

## Backend requirements

- Reads a plain-text script file with `Host: ` turn labels (see
  `script-conventions.md`).
- Writes an MP3 (or anything ffmpeg can convert — adapt
  `synthesize.sh`).
- Single voice per channel is enough for v0.1; multi-voice dialogue
  is out of scope (the show is single-host by design).

## Parsing gotcha (learned the hard way)

Some TTS chunk parsers silently return empty audio when a turn label
is malformed — e.g. a full-width colon (`Host：`) or a missing space
(`Host:text`). `compose.py` enforces ASCII `Host: ` (colon + space);
if you write your own composer, enforce the same or validate labels
before synthesis.

## Silence at chunk boundaries

If your backend inserts long pauses between chunks, post-process:
detect silences over ~1.5s and compress them. `ffmpeg`'s `silencedetect`
+ `silenceremove` does it. Validate audio length against the script
before calling an episode done.
