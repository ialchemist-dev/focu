# Muse deployment handoff: manual Archive + secretary briefing

PR #22: feat/manual-archive-secretary-briefing.

This document is a deployment protocol, not evidence of changes to the
remote Muse VM, 06:14 America/Denver production cron, or production Artifact.

## VM checkout housekeeping — execute before deployment

At the **real Muse VM** run:

    cd ~/workspace/focu
    git status --short
    git branch --show-current
    git fetch origin

If clean, switch the long-lived checkout from the old v0.4 branch to main:

    git switch main
    git pull --ff-only origin main

If locally modified, preserve all edits and work in a separate worktree.
Never force-switch, reset, stash, or delete unknown content. Never touch
databases, media deliveries, evidence, source subscriptions, or credentials.

To test the PR branch without altering the production checkout:

    git worktree add ~/workspace/focu-pr22 origin/feat/manual-archive-secretary-briefing

## Reader behavior

Inbox cards expose separate Read and Archive actions; article readers have
Archive immediately accessible in the toolbar. Manual Archive writes the
existing localStorage key focu:content-consumption:v1 with status consumed,
via manual, and the current ISO timestamp; the item leaves Inbox at once.
Archived cards and archived article views expose Restore. Reading-time,
audio-ended and native read-aloud auto-completion paths remain intact.

Do not change the production podcast Artifact as part of this PR. Cross-build
WebView storage persistence is out of scope and remains partially verified.

## Style: exactly one editable file

The authoritative file is references/briefing-style.md. It includes all
editable voice/persona rules and a dated changelog. To modify the voice,
edit this one file, append the owner's dated feedback, commit, then generate
a new episode. No second, provider-only personality prompt is permitted.

The daily pipeline in focu.daily.pipeline.compose loads this file on
every new composition, emits a separate section for every source report
item, and writes channel-briefing-qc.json. The finalization stage refuses
audio without a matching passed QC record. Already finalized scripts are
immutable historical outputs.

## Wire the actual 06:14 Denver job

The production cron command exists on the Muse VM, not in this GitHub repo.
Inspect the exact command in Muse scheduler/crontab/service first.

- If the 06:14 job calls scripts/run-daily.sh or
  python -m focu.daily.cli run, the composer now reads the style file
  automatically once the updated checkout is deployed.
- If it calls the Open Notebook provider from an agent command, switch to
  the versioned style prompt generation and transcript QC below.
- Use only a solo speaker profile. Keep registered sources and schedule
  unchanged. Record the actual job command and style SHA from its run log.
- Until this is checked on the VM, production-cron integration is UNVERIFIED,
  even if code CI is green.

## Generation and QC from real source/research units

Save the full report as an array of objects with stable id/content_id, source,
title, body and origin_kind: registered_source, requested_research, or
interest_follow_up. user_initiated is an alias for requested_research.

    python -m focu.briefing prompt \
      --units /private/complete-report-items.json \
      --output /private/briefing-prompt.txt

    focu podcast generate \
      --briefing-units /private/complete-report-items.json \
      --episode-name "Personal update" \
      --episode-profile solo_expert \
      --speaker-profile <AVAILABLE_SOLO_VOICE>

Wait for the real provider job, then run the QC-gated delivery, not the older
unvalidated generic podcast path:

    focu deliver --evidence-id <REAL_EVIDENCE_PACK_ID> \
      --job-id <REAL_JOB_ID> \
      --output-dir /private/delivery/new \
      --briefing-units /private/complete-report-items.json

The generated transcript must preserve all literal headlines, hard numeric
tokens and source attribution in each section. The code also rejects listed
show phrases. If QC fails, regenerate or flag the item rather than delivering
it. Run a human/agent evidence review for unsupported assertions: automated
checks alone cannot prove factual accuracy.

## Reproducible sample and style-diff demonstration

The sample is explicitly **synthetic fixture data**, not news or a real
user-listened podcast:

    python -m focu.briefing render \
      --units examples/secretary-briefing-demo-units.json \
      --output /tmp/focu-secretary-script.txt

    python -m focu.briefing qc \
      --units examples/secretary-briefing-demo-units.json \
      --script /tmp/focu-secretary-script.txt

The output must equal examples/secretary-briefing-demo-script.txt.
It covers five items and their figures: 948, 20, 5,034, 32, $1.2M and 17%.

The offline test test_editing_style_file_changes_both_script_and_prompt_without_code
edits only a disposable copy of references/briefing-style.md:
it changes the opening from "Here's what came in." to "A brief update for you."
and appends a dated changelog entry. The generated script and provider prompt
both change; source coverage remains complete. This demonstrates the owner
can adjust tone without changing Python code.

This short synthetic sample does not establish the real 5–8-minute daily
duration target. Real source reports should be tested on the Muse VM with
the actual generation profile and a complete post-generation QC report.
If a report exceeds time budget, flag that rather than dropping source items.

## Acceptance boundary

The PR must pass Python tests, HTTP fixtures, publisher tests, inline JS syntax
and reader behavior. Manual Archive must also be checked on iPhone.

Do not modify examples/sources.yaml, the production podcast library Artifact,
old audio, evidence packs, databases or the 06:14 schedule time.

Do not claim the Muse checkout was switched or the daily job rewired until the
real VM command and logs have been inspected.
