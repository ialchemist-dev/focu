# The Few

Your sources. Your podcast. Every day.

The Few turns only the sources you choose into a daily script and, with a
configured TTS backend, an MP3. No trending feeds or unsolicited sources.

## Status

v0.2 M1 foundation: persistent URL identities, SQLite backlog, cross-day
coverage, frozen episode inputs, resumable TTS, and a host-independent CLI.
The composer is still a deterministic skeleton: it reads the available text
without an LLM, translation, feedback learning, or long-body summarization.
Those capabilities are planned in [docs/V0.2-PLAN.md](docs/V0.2-PLAN.md).

RSS and blogs with an RSS feed are supported. YouTube is experimental and
requires optional dependencies. HTML-only blogs, X and LinkedIn are not
implemented; examples keep them disabled rather than claiming a successful
fetch. RSS scans the available feed window; old items removed from that feed
cannot be backfilled by this version.

## Install and run

M1 supports Linux/macOS and Python 3.10+. Run these commands from the repo:

```bash
git clone https://github.com/ialchemist-dev/the-few.git
cd the-few
python3 -m venv .venv
.venv/bin/python -m pip install -e .
cp examples/sources.yaml sources.yaml
# Edit sources, timezone and channel settings first.
.venv/bin/few run --text-only --dry-run --json
.venv/bin/few run --text-only --json
.venv/bin/few status --json
```

`--text-only` explicitly chooses text as the final artifact. To generate
audio, install ffmpeg/ffprobe and configure `tts_argv` as described in
[references/tts-backends.md](references/tts-backends.md), then omit this flag.
Missing or failed TTS does not count as a successful audio episode.
Use the same mode when resuming a date; text and audio completion are distinct.

All commands accept `--config` and `--data-dir`. Defaults are `sources.yaml`
and `data` in the working directory. Compatibility scripts keep repo-relative
defaults and support the same overrides:

```bash
THEFEW_PYTHON="$PWD/.venv/bin/python" ./scripts/run-daily.sh --text-only --json
```

Use only one scheduler. For example, at 07:14 in the machine's timezone:

```cron
14 7 * * * cd /absolute/path/to/the-few && .venv/bin/few run --text-only --json >> data/cron.log 2>&1
```

Create `data` before installing this cron entry. Config `timezone` determines
the episode date; cron's timezone determines the trigger time. Resume a failed
date with the same `--date`, mode and content config. A completed date is a no-op.
Never treat generation as proof of delivery or listening.

## Upgrading v0.1 data

Stop the old scheduler while importing. Do not run the new pipeline over old output directories. The CLI refuses to
initialize over legacy files. Import into a separate directory:

```bash
.venv/bin/few import-legacy --config sources.yaml --from-dir data --data-dir data-v2 --json
```

This copies the old state and outputs into a backup, imports snapshots from
configured sources, and ignores unreliable old cursors. By default it registers
no historical coverage. Add `--register-coverage` only when you explicitly
attest those episode snapshots as complete. That option requires scripts and,
in audio mode, MP3s, but does not infer delivery/listening or validate legacy
speech. Preserve original source names in config for matching. Future commands
must use `--data-dir data-v2`. See [references/architecture.md](references/architecture.md).

## For agents

[SKILL.md](SKILL.md) is the entry point. Muse, OpenClaw and other shell-capable
hosts use the same CLI and JSON contract; no host-specific installer is claimed.
Agents may submit units from configured sources with `ingest --input-units`.
[docs/ONBOARDING.md](docs/ONBOARDING.md) provides the existing setup questions.
Shared lists currently live in `examples/groups`; versioned import/export and a
marketplace registry are planned, not implemented in M1.

## Verify

```bash
.venv/bin/python -m unittest discover -s tests -v
```

The suite covers URL collisions, RSS repeat/ordering, transactional cursor
rollback, backlog, crash recovery, audio validation, source boundaries and
process locks. Audio tests require ffmpeg/ffprobe.

MIT — see [LICENSE](LICENSE).
