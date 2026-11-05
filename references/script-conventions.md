# Script conventions

The only current editable script voice and presentation policy is
[briefing-style.md](briefing-style.md).

Do **not** use the retired "generic podcast host" conventions. The owner's
format is a direct, single-person secretary's briefing, not a public show.

Both `focu.daily.pipeline.compose` and
`python -m focu.briefing prompt --units ...` consume the versioned style
file; the result is checked with `focu.briefing.validate_script`.

The `Host: ` turn prefix is a technical compatibility label for the
single-speaker TTS pipeline, not a performance cue or a second voice.

Complete input items and original hard figures are never deliberately
omitted merely to meet a time budget. An over-budget script is flagged for
review, not silently shortened.

Historical compatibility: scripts from older frozen episodes should not be
rewritten as part of this change. Only new compositions use the new style.
