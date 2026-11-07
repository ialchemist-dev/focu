# Prompt templates (v0.1 — framework; voice tuning comes next)

The composer (`scripts/compose.py`) fills these templates. Keep prompts
here, not in code.

## Compose: single-person secretary briefing

The **sole editable voice/style source** is [briefing-style.md](briefing-style.md).
The old generic podcast-host instructions have been retired.

The daily composer reads that file at generation time through
`focu.briefing.read_style`. Muse/Open Notebook should use the same file by
invoking:

```bash
python -m focu.briefing prompt --units /private/path/complete-units.json --output /private/path/briefing-prompt.txt
python -m focu.briefing qc --units /private/path/complete-units.json --script /private/path/generated-script.txt
```

If QC fails, revise/recompose; never quietly drop items or hard figures.
For a change of tone, edit only `references/briefing-style.md` and
append its dated changelog. Other prompt sections below concern selection and
source text, not the speaker's voice.

## Digest: rank and filter (used by digest.py when a channel overflows)

```
You are filtering a daily digest. Given {n} candidate items (title,
source, excerpt, published_at), pick the ones worth a {max_minutes}-
minute episode. Drop: press-release rewrites with no new information,
duplicate coverage of the same event (keep the earliest or the most
detailed), items older than 48h unless genuinely significant. Return
the kept item ids in order, newest first, with one line each saying
why it survived.
```

## Ingest: per-item summary (used when a body is too long for the digest)

```
Summarize the following {kind} from {source} in 5-8 sentences,
{language}. Keep: the core claim or event, key numbers, named people,
and one quotable detail. Drop: boilerplate, ads, nav text. Do not add
context from outside the text.
```

## Notes for the next iteration

- v0.1 optimizes for correctness (grounding, format, no meta-talk).
- The known next step is naturalness: varied sentence rhythm, spoken
  transitions, host personality without filler. Tune here, re-run
  `compose` on a saved `-units.json` snapshot — no re-ingest needed.
