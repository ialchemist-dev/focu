# Scheduling

The pipeline is cron-shaped: one run per day, unattended.

## Cron

```cron
14 7 * * * /path/to/focu/scripts/run-daily.sh >> /path/to/focu/data/cron.log 2>&1
```

`run-daily.sh` is idempotent per date: re-running the same `--date`
re-fetches only items newer than the watermark (usually zero), so a
retry never duplicates an episode.

## What the scheduler must guarantee

- One run per calendar day. If a run fails mid-pipeline, the next run
  (or a manual `--date` re-run) resumes cleanly: ingest advances
  watermarks only for items actually fetched; compose and synthesize
  overwrite that date's outputs.
- Logs: stdout goes to `data/cron.log`; per-source ingest warnings go
  to stdout too (grep for `skipped`).
- The scheduler never edits `sources.yaml`. Source changes are the
  user's job.

## Agent-run alternative

If the host agent has its own scheduler (e.g. Muse cron), schedule
"run `./scripts/run-daily.sh`" as a daily task instead of system cron.
Same contract: one run per day, logs kept, failures reported not
hidden.
