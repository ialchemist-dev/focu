# Scheduling and retries

Use one scheduler: system cron or the host agent's scheduler. Install Python
in a venv, use an absolute interpreter/CLI path, and choose a data directory.
Create the log directory before setting up redirection.

```cron
14 7 * * * cd /absolute/path/to/the-few && .venv/bin/few run --text-only --json >> data/cron.log 2>&1
```

Trigger time uses the scheduler/machine timezone. The episode date uses config
`timezone` (UTC default). `--date YYYY-MM-DD` overrides it, with strict date
validation. Every writer acquires the same kernel lock; lock contention returns
exit 5 rather than starting another process. Do not install both scheduler types.

A finalized date is a no-op. A failed date resumes its frozen selection and
script; repair TTS runtime settings and retry that same date. Earlier unfinished
episodes reserve their content; `few status --json` identifies dates to resume.
Use the original content config/output mode. Collection may overlap safely, but
no finalized episode is replaced or marked played/delivered by generation.

Exit codes: 0 success (including explicitly degraded source reports), 2 invalid
configuration/frozen run, 3 unavailable sources/runtime I/O failure, 4 episode
failure, 5 concurrent writer. JSON stdout has schema_version/status and contextual
reports; do not interpret a degraded run as all sources having succeeded.
Host-specific scheduler registration and uninstall instructions are M4 work.
