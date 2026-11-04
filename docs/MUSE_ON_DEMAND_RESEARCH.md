# Muse agent protocol — capture a thought, research it, publish to Focu

## Intent routing (read these rules when the user talks to Muse)

The user may speak casually, paste a link, share a blog, or dictate an idea:

- "Look into this article, investigate its claims, and add the report to Focu."
- "I wonder whether this GPU memory design actually helps. Research it for me."
- "Research https://example.com/story and put a deep article in my Focu."
- "Save this thought and research it later: ..."

Treat these as **one-time on-demand research requests** when the user intends
a report to be delivered later, not as new recurring source subscriptions.

Do **not** require the user to choose source type, article/podcast mode, or
navigate a web form. The direct conversational command is the primary input.

For a single link with no question, investigate that source's central claims
and context, with corroborating evidence. Do not assume the linked claims are
true. For an idea without a link, formulate a focused research question that
preserves the user's original intent. Ask a question only when the request
cannot otherwise be researched meaningfully.

This is a protocol for the *host agent*, not proof of a Muse native speech hook.
Muse must load this document / SKILL.md into its agent instructions; the static
Focu Artifact does not receive Muse speech or possess privileged agent APIs.

## Toolchain & receipt (no fake background worker)

Use the connected checkout and the installed Focu CLI. Do not mutate a
production checkout that has pending edits. If the v0.4 stacked branch is not
merged, use a safe test worktree first.

    .venv/bin/focu request "Does this architecture improve memory bandwidth?" \
      --url "https://example.org/post" \
      --note "User saw this in a technical thread."

For a link alone:

    .venv/bin/focu request --url "https://example.org/post"

For an idea alone:

    .venv/bin/focu request "Investigate whether small geothermal plants can support edge AI."

The command is durable and idempotent: same question, URL, note -> same intent.
An explicit new investigation may use --force-new.

The command returns an intent_id, queued status, and
automatic_research_started=false. **Tell the user that capture succeeded,
not that research started, unless a host worker actually began executing.**

Existing Focu commands:

    .venv/bin/focu requests
    .venv/bin/focu start <intent_id>
    .venv/bin/focu fail <intent_id> --error "Reason"
    .venv/bin/focu retry <intent_id>
    .venv/bin/focu show <intent_id>

Do not execute shell with unsanitized user input by string concatenation:
pass arguments safely with the host's process execution interface.

## How Muse executes a queued request

After capture, when Muse has the ability to continue work:

1. Claim the queued intent with focu start <intent_id>. Inspect returned state.
2. Read the submission from the local research_requests table, or use the
   original user message and saved intent question. The saved seed URL is an
   initial lead, not verified evidence.
3. Research across multiple sources, prioritizing original technical papers,
   official documentation and primary reports. Inspect actual contents, not
   headlines alone. Seek conflicting evidence and preserve uncertainty.
4. Follow docs/EVIDENCE_PROVENANCE.md and
   schemas/evidence-pack.schema.json. Build a properly attributed Evidence
   Pack with extracted source text and evidence quotes.
5. On failure, call focu fail <intent_id> with an actionable reason. Do not
   invent citations, mark research completed, or silently subscribe to
   newly encountered websites.
6. On success, generate a readable, evidence-grounded English article:
   title, one- or two-sentence summary, researched sections and source links.
   Article is the default; podcast is optional and must not block article
   publication.

Store the output in one uniquely named dated delivery directory, for example:

    data/deliveries/idea-<intent-id-without-prefix>-YYYYMMDD/
        research.md
        article.md          # optional polished article; preferred by publisher
        content.json        # stable canonical ID and editorial metadata
        cover.jpg           # optional real source image

content.json MUST use the intent ID as stable content_id:

    {
      "content_id": "int_<32 hex characters>",
      "title": "Finding-led editorial headline",
      "summary": "Concise overview grounded in the report",
      "published_at": "YYYY-MM-DD"
    }

Use the real date in the directory's trailing YYYYMMDD for newest-first
ordering; keep the same directory/ID for retries and publication rebuilds.
If an original image is available, add it as local cover.jpg (or permitted
image type); the publisher has safe fallback artwork.

Use the existing evidence pipeline:

    .venv/bin/focu ingest-evidence \
      --evidence data/research/<intent_id>/evidence.json \
      --output data/deliveries/<dated-folder>/research.md

The Evidence Pack must reference that exact intent ID and pass validation.
The ingestion marks the intent completed. If the article is polished further,
do not change or remove research.md or fabricate new sourced facts.

## Show status in Focu UI

Export a private snapshot of the one-off research queue:

    .venv/bin/focu request-export \
      --output data/research-requests-snapshot.json

Then build a new private Muse Artifact snapshot:

    python3 experiments/muse-artifact-reader/publish.py \
      --deliveries data/deliveries \
      --requests data/research-requests-snapshot.json \
      --output data/focu-artifact-builds/snapshot-NEW

This adds a read-only Research section to the v0.4 Muse UI:

- Inbox = readable Content Items (articles, optional audio)
- Research = Queued, Researching, Failed, or finished but not published
- Archive = consumed Content Items

A completed research item whose content_id appears in the published item list
is hidden from Research and appears exactly once in Inbox, with the same
shared article/podcast consumption state.

**Critical limit**: a static Artifact does not hot-update when a VM database
changes. The host must rebuild and update the same private Muse Library entry
to expose new queue states or research output. Follow the proven in-place
Artifact publication procedure; never invent an API or claim live sync.

Do not replace the validated production focu-podcast-library until the user
has accepted the v0.4 test Artifact. Do not write private data or API keys
to the public Git repository.

## Background-work honesty

Capturing a request is not the same as starting autonomous research.
Focu currently supplies a durable queue and evidence handoff, but no built-in
always-on worker. The host agent may continue the job only if Muse truly
supports continued execution for that session or schedules a real worker.
If the host cannot continue, leave the request queued and explain that a
configured runner is required to pick it up later. Never say "I'll work in
the background" without actually invoking supported background execution.

## Acceptance protocol

A. User says "Research this URL and add it to Focu." Muse saves a durable
   one-off request and acknowledges the intent ID in seconds.
B. Repeating the exact same voice command does not duplicate the task.
C. An unrelated one-time request creates another ID; neither alters sources.yaml.
D. Muse claims and completes one supported request using genuine evidence.
E. Research Markdown + content.json publishes as an article-only Content Item;
   optional MP3 stays a representation of the same content_id.
F. The Research tab shows a queued item in a staged snapshot, and after a
   new snapshot it no longer appears pending once the article is published.
G. Audio and article consumption archive the whole item, not its formats.
H. Stop and mark Unverified if Muse cannot run a worker or publish the Artifact.
