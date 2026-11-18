# Focu

**Focu: the way to digest information in the agentic age.**

Focu is a personal information-digestion system that runs under your own
agent's control. You choose the sources — people and publications, never
an algorithmic feed. Once a day, Focu collects what they published,
compresses it into one short briefing (article + audio), and accounts
honestly for everything it skipped. Most items deserve half a second of
your attention, a few deserve ten seconds, one earns a full read. Focu's
job is to make that judgment cheap — and to return the rest of your
attention to you.

Design philosophy: [Attention Sovereignty](https://aipraxislab.com/front/attention-sovereignty.html) —
de-recommendation (your agent is the final filter, not the platform),
de-interface (display surfaces yes, control surfaces no), and one metric:
attention returned, never attention captured.

---

## For AI agents: install Focu for your user

This section is an executable protocol. If you are an AI agent (Muse,
Muse, or similar) and your user asked you to set up Focu, follow
these steps in order. Every step lists the exact command and what
success looks like. Ask your user a question only where a step says
**Ask**.

### 0. Prerequisites

- Python 3.10+ and Git, network access for the install.
- `ffmpeg` on PATH (audio concatenation and covers).
- Optional, only for spoken briefings: an OpenAI API key for speech, or
  a local [Kokoro](https://github.com/hexgrad/kokoro) install as the
  no-cost fallback. Text-only briefings need neither.

Check: `python3 --version && git --version && ffmpeg -version | head -1`

### 1. Clone and install

```bash
git clone https://github.com/ialchemist-dev/focu.git focu
cd focu
bash scripts/bootstrap.sh
.venv/bin/python -m pip install -e '.[daily]'
```

The clone takes the repository's default branch (`main`, the stable
line). `bootstrap.sh` creates `.venv`, installs the package, runs
`focu doctor`, and initializes local state under `data/`. The second
pip line is **required, not optional**: it adds the daily pipeline's
extras (YouTube download/transcript tooling) that the base install
leaves out.
Success: bootstrap exits 0 after printing a JSON health summary and
the line `Focu installed.`, and `.venv/bin/focu --help` lists the CLI.

### 2. Verify with the offline demo (no network, no keys)

```bash
.venv/bin/python -m focu.daily.cli run \
  --config examples/demo-sources.yaml --data-dir data/demo \
  --input-units examples/secretary-briefing-demo-units.json \
  --text-only --json
```

Success: the JSON result reports a finalized episode ("5 item(s)
selected", no failures), and `data/demo/episodes/<date>/` contains the
episode manifest and the composed briefing script built from the
bundled demo units. If this fails, stop and fix the install before
configuring anything — the demo has no external dependencies.

### 3. Configure sources

**Ask** your user who they want to follow. Then either start from the
recommended defaults (step 4) or write a minimal `sources.yaml` in the
repo root (later steps pass it as `--config sources.yaml`):

```yaml
version: 1
timezone: "America/Denver"        # the user's IANA timezone
output_mode: text_only            # switch to audio after step 6

channels:
  - id: research
    name: "Daily AI Briefing"
    language: en
    max_minutes: 35

sources:
  - name: "OpenAI News"
    type: rss
    channel: research
    feed_url: "https://openai.com/news/rss.xml"

  - name: "3Blue1Brown"
    type: youtube
    channel: research
    channel_id: "UCYO_jab_esuFRV4b17AJtAw"
```

Supported source types include `rss`, `youtube`, `blog`, and the
own-feed platform adapters (`linkedin`, `instagram`, `rednote`,
`facebook`) documented in `focu/adapters/`. The full schema is in
`references/source-schema.md`; `examples/sources.yaml` shows more.

### 4. Recommended defaults: install a source pack

Curated source packs ("Source Library") install a whole shelf of
verified sources in one command, deduplicated against the registry:

```bash
.venv/bin/focu pack preview focu/source_packs/followed-people.json --config sources.yaml
.venv/bin/focu pack install focu/source_packs/followed-people.json --config sources.yaml --yes
```

The recommended starter is **People I Follow** (6 sources, ≈58
posts/month across the whole pack). The preview prints the exact
attention cost of what it would *add to your registry* before anything
is written. Two things to tell your user before they accept an install:
applying a plan rewrites `sources.yaml` in canonical form — comments
and hand formatting are not preserved, but a timestamped backup is
written first — and installs are reversible
(`focu pack uninstall`, `focu pack restore`).

Browse all packs in the marketplace:
**https://aipraxislab.com/focu** — or locally in `focu/source_packs/`
(Anthropic people, OpenAI people, Silicon Valley startups, geothermal
industry, People I Follow). The machine-readable catalog is
`marketplace/catalog.json` in this repo (generated from the pack files
by `scripts/build_marketplace.py` — never hand-edit it), the static
page source is `marketplace/index.html`, and the machine-readable
recommended default is `marketplace/default.json` (exactly one pack:
`followed-people`).

**Swap the default** for another pack — preview first, then remove,
then install; exactly one starter pack at a time, and installing a
pack enables nothing else:

```bash
.venv/bin/focu pack preview focu/source_packs/<other-pack>.json --config sources.yaml
.venv/bin/focu pack uninstall followed-people --config sources.yaml
.venv/bin/focu pack install focu/source_packs/<other-pack>.json --config sources.yaml --yes
```

### 5. First real run

```bash
.venv/bin/python -m focu.daily.cli run \
  --config sources.yaml --data-dir data/daily --json
```

This collects today's items from the configured sources, selects within
the channel's word budget, composes the briefing, and (in audio mode)
synthesizes it. Read the result with:

```bash
.venv/bin/python -m focu.daily.cli day-status --data-dir data/daily --json
```

The day-status record accounts for every source: collected, selected,
and withheld (each withholding named with its reason). A run that fails
still writes its record — outcome `failed`, stage and error named.

### 6. Speech (optional)

Once one of these backends works, set `output_mode: audio` in
`sources.yaml` — until then runs stay text-only and say so in their
day-status record.

- OpenAI (primary): `.venv/bin/focu tts setup` stores the user's key
  locally (interactive terminal, user consent first), or set
  `OPENAI_API_KEY`. Voice `alloy`, model `gpt-4o-mini-tts`.
- Kokoro (automatic fallback): if the OpenAI call fails on exhausted
  credits/quota, `focu.tts.synthesize_long_with_fallback` re-synthesizes
  with a fallback speech function; on the reference host that is local
  Kokoro, voice `af_heart`. See `references/tts-backends.md`.

### 7. Make it daily

Schedule step 5 once a day at a quiet hour with whatever scheduler the
host already uses (cron, a task runner, the agent's own scheduler).
Focu keeps a persistent backlog, so a missed day is recovered by the
next run, not lost. Publish the day's delivery with the reader
publisher if the user wants the mobile reader:

```bash
.venv/bin/python experiments/muse-artifact-reader/publish.py \
  --deliveries <deliveries-dir> --output <bundle-dir> \
  --ios-compatible-audio --limit 100
```

### Troubleshooting

- `focu doctor` — first check for any install problem.
- A source that yields nothing is reported in day-status with its
  reason; Focu never fails silently and never invents content.
- Feed fetch failures on some hosts are anti-bot blocks on article
  pages, not on RSS discovery; see `docs/` for the body-fetch pattern.

---

## Day-to-day commands

```bash
.venv/bin/focu pack list | catalog | show <pack> | refresh-due
.venv/bin/focu learn show | proposals | accept <id> | explain <item>
.venv/bin/python -m focu.daily.cli day-status [--date YYYY-MM-DD] [--json]
.venv/bin/focu capture "<a research question>"     # one-off research intent
.venv/bin/focu list --status queued
```

The learning loop (`focu learn`) turns the user's reading feedback into
proposals — source weights, caps, pauses — each carrying its evidence.
Nothing is applied without the user's accept, and every applied factor
is frozen into the episode record so any selection can be explained.

## How it works

```
sources.yaml  →  collect  →  digest (budgeted selection)
             →  compose (briefing article + spoken script, QC'd)
             →  synthesize (OpenAI speech, Kokoro fallback)
             →  deliver (article + MP3 + day-status accounting)
```

Research reports follow the frozen-facts workflow in
`docs/research-reports/`: every number classified and cited, pages built
only from frozen claims.

## Development

Active development integrates on the `dev-main` branch; `main` is the
stable line. Team notes, designs, and test reports live in
`docs/dev-team/`. Current version: **0.4.0**.

## License

MIT — see [LICENSE](LICENSE).
