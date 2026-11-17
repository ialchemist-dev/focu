# Focu learned preferences

**Version:** 2026-11-17.1
**Owner:** one person (Focu's owner)
**Change discipline:** this record is written only by owner acts — a preference the owner stated directly (`owner-stated`, entered by hand or at his word), or a proposal the owner accepted (`owner-accepted`, written by `focu learn accept` and citing its proposal id). The learning engine proposes; it never writes here on its own. Deleting an entry is done by removing it from this file or by the owner's instruction; the file is the source of truth. A record that fails validation yields *no* learned influence and a visible error — never a guess.

## Machine-readable settings

The YAML block below is the single source of truth for learned influence on selection. Entry IDs are stable (`lp-NNN`); kinds are `source_pause`, `source_cap`, `source_weight`, `topic_weight`, `standing_note`. `standing_note` entries carry context for the agent and have no scoring effect.

```yaml
version: "2026-11-17.1"
entries: []
```

## Changelog

- **2026-11-17 — v2026-11-17.1:** Record created (Phase 1 of the learning loop, `docs/dev-team/learning-design.md`). Empty of learned entries: nothing has been proposed or accepted yet.
