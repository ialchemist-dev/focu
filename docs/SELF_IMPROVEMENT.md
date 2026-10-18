# Self-improvement foundation: explicit feedback (experimental)

This slice is a **feedback event ledger**, not a self-training or self-modifying agent. The host agent records explicit user feedback about an episode, evidence pack, observation or research intent. Events are stored locally in SQLite and can be listed for later offline evaluation.

```bash
.venv/bin/python -m focu.feedback record --target-type episode --target-id 2026-10-17/research --kind too_long --note "Reduce repetition"
.venv/bin/python -m focu.feedback list --target-type episode
```

Kinds: `useful`, `not_useful`, `incorrect`, `too_long`, `missed_important`, `other`.

Only record feedback actually provided or explicitly confirmed by the user. Do not interpret passive silence, skipped playback, or agent self-evaluation as user preferences. Do not change sources, Watch scope, prompts, skills or delivery rules based on this ledger alone. Feedback may be sensitive; keep the database local and out of Git.

**Next research/implementation steps:** define evaluation fixtures and quality metrics (factuality, usefulness, missed-important-event rate, attention cost, token/time cost), generate candidate workflow improvements, test against held-out episodes, require explicit user approval for scope changes and reversible promotion for strategy changes.
