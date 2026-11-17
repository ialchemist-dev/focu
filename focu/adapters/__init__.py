"""Platform adapters: external collection -> Focu daily units.

Each adapter implements Seam 1 of the platform contract (infra design
B.5): a platform-specific collector side that adapts one day of the
owner's own material into zero or one digest unit per registered source,
in the exact ``{source, title, url, published_at, body}`` shape the
daily pipeline ingests (the LinkedIn emitter's shape). Adapter failure
never blocks the briefing; Focu stores no platform credentials, ever.
"""
