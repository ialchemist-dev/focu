# Focu Exchange — backend design: source-pack schema v1, import flow, validation, versioning

**Author:** backend developer agent, 24h dev run, wave 1 (design + data only; no code changes this wave)
**Status:** design for PM/infra review. Working name "Focu Exchange" per STATE.md (owner may veto/rename).
**Scope:** the backend contract for curated source packs: schema v1, one-step install into
`sources.yaml`, dedupe, undo, validation, and versioned updates. UI surfaces are the UI dev's
deliverable; this document defines the data and CLI/API behavior they render.

---

## 1. Grounding: what already exists (verified in `~/workspace/focu-dev-checkout`, dev-main base)

The marketplace is **not** greenfield. Four existing pieces define the constraints:

1. **The pack data model already exists, twice.**
   - Bundled: `focu/source_packs/anthropic-personal-blogs.json` (data directory inside the
     package; note it has no `__init__.py` — it is a resource dir addressed by path from
     `focu/reader.py: PACKS = Path(__file__).with_name('source_packs')`).
   - Published: the owner's site Source Library (`site-source-catalog.json` +
     `site-pack-anthropic-personal-blogs.json` in `~/workspace/focu-dev/`) — byte-for-byte the
     same pack shape, plus a catalog wrapper (`schema_version`, `packs[]` with
     `id/name/file/summary/eyebrow`).
   - Pack shape today: pack `{id, version (semver string), name, description, categories[],
     coverage, verified_at, sources[]}`; source `{id, name, type, channel, site_url, feed_url?,
     affiliation_evidence, affiliation_status, notes, readiness, verified_at, enabled,
     max_items_per_day}`.

2. **Reader-side subscriptions already implement pinning and dedupe.**
   `focu/reader.py: ReaderStore` —
   - `packs()` loads every `focu/source_packs/*.json` and annotates `subscribed_version`.
   - `subscribe(pack_id, enabled, version)` requires the caller to name the **exact** pack
     version, then snapshots the **entire pack payload** into the `reader_subscriptions`
     SQLite table. Re-subscribing the same version is idempotent; subscribing a stale version
     after an update raises (`tests/test_reader.py:
     test_overlapping_packs_pin_membership_and_unsubscribe` is the contract test).
   - `sources()` merges all subscribed packs' sources, deduped by
     `canonical_url(feed_url or site_url)`, and annotates each source with `groups`
     (the list of pack ids providing it). Unsubscribing one pack therefore preserves sources
     another pack still provides.
   - `focu/reader_server.py` already serves `GET /api/packs`.

3. **The daily pipeline has its own, separate registry: `sources.yaml`.**
   `focu/daily/config.py: load_config()` is the gatekeeper. Facts that bind this design:
   - Source `type` must be in `KNOWN_TYPES = {"rss", "blog", "youtube", "x", "linkedin"}`
     (plus legacy `anthropic` + `section`, normalized in-memory to a blog source).
   - Enabled source **names must be unique**; `channel` must match a declared channel id.
   - Every enabled source gets a durable identity: `focu/daily/identity.py: source_url(src)`
     picks the per-type locator, `canonical_url()` normalizes it, and
     `stable_id("src", canonical_url)` becomes `source_id`. **Duplicate identities are a hard
     error** ("duplicate source identity; merge into one subscription") — so an installer must
     dedupe *before* writing, or the daily pipeline refuses to start.
   - Disabled sources (`enabled: false`) may lack locators and skip validation — the pack
     format's disabled entries map onto this exactly.
   - `load_config` tolerates unknown extra keys on source dicts (it reads the keys it knows),
     but see §4.3: provenance still does **not** belong in `sources.yaml`.

4. **Feed fetching/parsing already exists.**
   `focu/source_collection.py: collect()` + `parse_feed()` fetch a feed with a bounded,
   identified request (`User-Agent: Focu/0.2 (+explicit source collection)`, 15s timeout,
   2 MB cap) and accept only RSS/Atom/RDF roots. The liveness checker in §6 reuses
   `parse_feed` unchanged.

**The gap this design fills:** the reader subscription world (SQLite, `focu reader
subscribe`) and the daily-pipeline world (`sources.yaml`) are disconnected. The only bridge
today is manual: the site's "Copy Focu YAML" export and the agent contract in
`site-source-library-AGENT_GUIDE.md` ("prepare a deduplicated proposed edit… ask for explicit
permission before modifying subscriptions"). Focu Exchange turns that contract into a
first-class, testable CLI flow: `focu pack install`. `docs/READER_MARKETPLACE_PLAN.md`
already specifies the target semantics (pinned versions, explicit updates, dedupe by
canonical locator, unsubscribe preserves shared sources); this design implements them for
the `sources.yaml` side and keeps the reader side as-is.

## 2. Design principles (from `attention-sovereignty.md`)

- **Follow people, not platforms.** The pack unit of curation is a *person with an
  author-owned site*. Schema v1 therefore promotes `person`, `role`, and `org` to first-class
  fields, and keeps `affiliation_evidence` — identity evidence is part of the data, never a
  popularity signal. There is no ranking field, and none may be added.
- **The user's agent is the final filter; the human judges, the machine operates**
  (de-interface). Install is one command. Everything judgment-shaped — what will be added,
  what was skipped and why, what it will cost in attention — is computed *before* the write
  and shown as a preview. Everything mechanical (fetching, canonicalizing, merging,
  backing up, validating) is done by the tool without further questions.
- **Attention cost is stated up front.** Every source carries a cadence estimate; the preview
  totals it ("this pack adds ≈5.5 posts/month, of which ≈4.3 is one weekly newsletter").
  Success is attention returned, so a pack that would flood the briefing must say so before
  it is installed, and per-source `max_items_per_day` caps remain the enforcement mechanism
  downstream (`focu/daily/config.py` defaults it to 5; the selection budget in the daily
  pipeline does the rest).
- **Fail closed, degrade loudly.** A pack that fails validation installs nothing. A feed
  that fails liveness installs as `enabled: false` with the failure recorded — never
  silently enabled, never silently dropped (the prototype's treatment of Dario Amodei and,
  in v0.1.0, Jan Leike is the precedent).
- **No silent mutation, ever.** Installing, updating, and uninstalling are explicit,
  previewed, and reversible. Discovery (a newer pack version existing) never changes a
  user's registry by itself — this restates the rule already written in
  `docs/ANTHROPIC_SOURCE_DISCOVERY.md` ("discovery never mutates an existing user's
  subscription") and the site AGENT_GUIDE contract.

## 3. Pack schema v1

Canonical form below. A JSON Schema will live at `schemas/source-pack.schema.json`
(alongside the existing `schemas/evidence-pack.schema.json` etc.) and is the normative
definition; this section is its readable summary.

### 3.1 Pack level

| field | type | req | notes |
|---|---|---|---|
| `schema_version` | int = 1 | yes | mirrors the site catalog's `schema_version: 1` |
| `id` | string, `^[a-z0-9][a-z0-9-]{1,63}$` | yes | stable across versions; matches catalog entry id |
| `title` | string | yes | canonical display name (site packs call this `name`; see compat) |
| `version` | semver string | yes | e.g. `"1.0.0"`; bump rules in §7 |
| `curator` | `{name, url?}` | yes | who stands behind the curation; the site packs predate this field (compat default below) |
| `description` | string | yes | one or two sentences |
| `tags` | string[] | yes | canonical (site packs call this `categories`; see compat) |
| `coverage` | string | yes | honest scope statement — what this pack is *not* (carried over from the prototype; required, because a people-pack that implies a census it didn't do violates the curation contract) |
| `verified_at` | date `YYYY-MM-DD` | yes | when the pack as a whole was last re-verified |
| `sources` | source[] | yes | may be empty only in a catalog stub, never in an installable pack |
| `unverified` | candidate[] | no | candidates that failed verification, **with reasons** (§3.3). Never installed. Formalizes the "Excluded or unresolved candidates" section of `docs/ANTHROPIC_SOURCE_DISCOVERY.md` |
| `attention_estimate` | `{posts_per_month, basis}` | no | curator-computed total for enabled sources; the installer recomputes it live and reports any drift |

### 3.2 Source level

Required for every source: `id` (slug, unique within the pack), `name` (display label —
this becomes the `sources.yaml` `name`, so it inherits the loader's uniqueness rule after
merge), `type` (must be in `focu/daily/config.py: KNOWN_TYPES`), `channel`.

| field | type | req | maps to / notes |
|---|---|---|---|
| `person` | string | for people-packs | the human's name when the source is a person; for org sources use `org` alone |
| `org` | string | no | employer / affiliation, e.g. `"Anthropic"` |
| `role` | string | no | e.g. `"Research Scientist — interpretability"`. Evidence for the role belongs in `affiliation_evidence` |
| `homepage` | HTTPS URL | yes* | canonical field name in v1; the prototype's `site_url` is the same datum (compat alias). *Required unless the source is feed-only |
| `feed_url` | HTTPS URL | for `type: rss` | the loader already hard-requires this for rss |
| `platform` | string | yes | where the content lives: `Ghost`, `Substack`, `WordPress`, `GitHub Pages`, `Hugo (self-hosted)`, `Self-hosted`, … — deliberately distinct from `type`, which is focu's *transport* (`rss`/`blog`/…). A Substack is platform=Substack, type=rss |
| `affiliation_evidence` | URL | for people-packs | author-owned page evidencing identity/role (carried from prototype) |
| `affiliation_status` | string | no | `current` / `self-described cofounder` / … (carried from prototype) |
| `cadence` | `{posts_per_month: number, basis: string, as_of: date}` | yes | `basis` is mandatory and must cite observable evidence ("feed's two newest items: 2026-01-22 and 2025-01-24"). An estimate without a stated basis is a validation error — this is the pack format's version of the house rule against invented numbers |
| `last_post_at` | date | no | newest item date observed at verification, when known |
| `verified_at` | date | yes | last date *this source* was fetched and checked |
| `readiness` | string | no | free-text collection status (carried from prototype; v1 validation *produces* this string for bundled packs, humans write it for curated ones) |
| `enabled` | bool | yes | `false` = listed for judgment, not installed active (no-feed and failed-liveness sources) |
| `max_items_per_day` | int ≥ 1 | no | default 5 (the loader's default); curators of high-volume sources should set it lower — see Adam Jones in the companion pack |
| `notes` | string | no | curator's note → becomes the `sources.yaml` `notes` |

### 3.3 Unverified candidates

`{name, homepage?, reason, checked_at}` — `reason` is mandatory and must say *which* test
failed (affiliation not established / not actually an employee / site has no blog or feed /
site could not be attributed to the person). Candidates are displayed in previews and pack
pages as excluded-with-reason. They are data, not a waiting room: nothing in the install
path may promote one without a new pack version that moves it into `sources` with full
verification fields.

### 3.4 Compatibility with the owner's site packs (hard requirement)

The v1 loader normalizes on read; writers always emit canonical v1:

- `name` → `title` (pack level), `categories` → `tags`, `site_url` → `homepage` (source
  level). If both forms appear they must agree, else validation error.
- Missing `curator` defaults to the publishing catalog's owner (for the AI Praxis Lab
  library: the site itself) and is flagged in `focu pack validate` output as a
  should-fix warning, not an error — the 2026-10-28 packs must keep loading.
- Missing `cadence` on a legacy source is a warning in `validate`, and the install preview
  shows "cadence unknown" rather than inventing one. New packs (schema_version 1 with a
  `curator` field) are held to the full bar: cadence with basis is required.
- Because the current reader code path (`ReaderStore.sources()`) reads `feed_url` /
  `site_url` keys directly, v1 writers emit **`site_url` alongside `homepage`** (same value)
  until the reader is migrated. The companion data file does exactly this.
- `focu/source_packs/anthropic-personal-blogs.json` (bundled, v0.1.0) remains valid under
  these rules; the companion deliverable `team/anthropic-people-pack.json` is its v1.0.0
  successor — same pack `id`, so the Exchange treats it as an *update* (§7), which is the
  migration path for the bundled copy in a later wave.

## 4. The install flow: pack → `sources.yaml` in one step

### 4.1 Commands (new `focu pack` group in `focu/cli.py`, beside `reader` and `daily`)

```
focu pack catalog list|add <catalog-url>|remove <id>
focu pack list [--catalog <id>]            # available packs + installed versions
focu pack show <pack-id> [--version X]     # full membership, cadence, unverified + reasons
focu pack validate <file|url>              # schema + URL + liveness report, no writes
focu pack install <pack-id|file|url> [--channel research] [--dry-run] [--yes]
focu pack update <pack-id> [--dry-run] [--yes] [--prune]
focu pack uninstall <pack-id> [--dry-run] [--yes]
focu pack restore [--backup <file>]        # undo from a timestamped backup
```

All commands print a human preview and, with `--json`, the same report as JSON (the agent
surface: an agent runs the command, shows the owner the preview, and applies on approval —
the AGENT_GUIDE contract, mechanized). `--dry-run` is the default posture for agents:
**install/update/uninstall without `--yes` after a preview is a design smell; the CLI asks
once, interactively, and agents pass `--yes` only after the owner has seen the preview.**

### 4.2 Install algorithm (implemented in new module `focu/packs.py`)

1. **Resolve & fetch** the pack (bundled dir `focu/source_packs/`, a catalog `file` URL, or
   a local path). Record its SHA-256.
2. **Validate** (§6): schema, URL hygiene, channel exists, per-source liveness for enabled
   rss sources. Any hard error → abort, nothing written.
3. **Load the current registry** with `focu/daily/config.py: load_config()` (this also
   yields each existing source's `source_id` — the dedupe key set).
4. **Plan** (pure function, fully unit-testable): for each pack source —
   - compute its identity exactly as the loader does (`identity.source_url()` →
     `identity.canonical_url()` → `stable_id("src", …)`);
   - identity already present → **skip-duplicate**, reported with the name of the existing
     source and, if known from the install manifest, which pack/manual entry provides it;
   - name collision with a *different* identity → hard error (the loader would reject the
     merged file; surface it in the preview instead, with a suggested rename);
   - `enabled: false` in the pack → planned as a disabled entry (locator optional, per the
     loader's disabled-source rule);
   - liveness failed in step 2 → planned as disabled with the failure appended to `notes`,
     even if the pack said enabled.
5. **Preview**: added / skipped-duplicate / added-disabled / excluded-unverified counts;
   per-added-source cadence and last-post date; total attention estimate; the exact
   `sources.yaml` diff. This is the judgment surface — nothing has been written yet.
6. **Apply** (on confirmation): copy `sources.yaml` → `sources.yaml.bak-<UTC timestamp>`;
   write the merged YAML to a temp file in the same directory; **re-load the temp file with
   `load_config()`** — if it raises, delete the temp file, leave the original untouched,
   report the loader error verbatim; else atomically rename over `sources.yaml` and append
   to the install manifest (§4.3).
7. **Report**: what was installed, the backup path, and the one-line undo command.

Channel assignment: a pack source's `channel` is used when that channel exists in the
user's config; `--channel` overrides for all sources in the pack; a pack naming a channel
the user doesn't have is a preview-level error with the fix offered ("create channel
`research`?"), never a silent remap.

### 4.3 Provenance: the install manifest (not `sources.yaml`)

`sources.yaml` stays a pure loader document — no pack metadata is written into it (extra
keys would flow into `load_config`'s `config_hash` and into every consumer of the config
dict, for zero loader benefit). Provenance lives in **`packs-installed.json`** beside
`sources.yaml`:

```json
{"packs": [{
  "pack_id": "anthropic-personal-blogs", "version": "1.0.0",
  "sha256": "…", "installed_at": "2026-11-17T09:00:00Z",
  "backup": "sources.yaml.bak-20261117T090000Z",
  "entries": [{"source_id": "src_…", "name": "Felix Rieseberg",
               "locator": "https://felixrieseberg.com/rss/", "enabled": true}]
}]}
```

`source_id` is the loader's own `stable_id`, so the manifest joins losslessly with the
registry, with `ReaderStore.sources()`'s `groups` annotation (same dedupe idea, reader
side), and with collected content downstream.

### 4.4 Undo

Two levels, both previewed:
- `focu pack uninstall <id>`: removes exactly the manifest entries for that pack **whose
  `source_id` is not also provided by another installed pack and was not present before
  this pack was installed** (the manifest records pre-existing ids at install time; manual
  entries are never removed). This mirrors `ReaderStore` unsubscribe semantics. The file
  write goes through the same backup → temp → `load_config` gate as install.
- `focu pack restore`: byte-level rollback to a named backup. This is the escape hatch for
  hand-edits gone wrong, and it is also previewed (it discards changes made since the
  backup — the preview lists them via the manifest + a name-level diff).

## 5. Dedupe rules (one identity, everywhere)

- The dedupe key is the loader's identity: `stable_id("src", canonical_url(source_url(src)))`
  from `focu/daily/identity.py`. `canonical_url` already strips `utm_*` and the known
  click-id parameters (`fbclid`, `gclid`, `dclid`, `msclkid`, `mc_cid`, `mc_eid`), drops
  fragments, lowercases scheme/host, normalizes YouTube video URLs and twitter→x.com.
- **Known divergence to fix in the implementation wave:** `focu/reader.py: canonical_url()`
  is a *different* function — it does not strip tracking parameters and it strips trailing
  path slashes, which `identity.canonical_url` deliberately preserves ("none of these
  equivalences is guaranteed for arbitrary publishers"). Two canonicalizers means the same
  source can dedupe in the reader and not in the daily registry. Recommendation: the pack
  flow (this design) uses `identity.canonical_url` only, since `sources.yaml` is its
  target; unifying `reader.py` onto it is a separate, test-guarded change (its
  subscription snapshots already store full payloads, so the blast radius is contained to
  `sources()` output). Flagged for the infra designer; not silently papered over here.
- Within a single pack, duplicate identities across two source entries are a validation
  error (the curator dedupes, not the user).
- Across packs, first installer wins the registry slot; later packs report the source as
  provided-by the earlier pack (manifest cross-reference), exactly like `groups` in
  `ReaderStore.sources()`.

## 6. Validation rules (`focu pack validate`, also install step 2)

Hard errors (install nothing):
1. JSON parses; conforms to `schemas/source-pack.schema.json`; `schema_version` supported.
2. Pack `id`/`version` present and well-formed; source ids unique within the pack.
3. Every URL field (`homepage`, `feed_url`, `affiliation_evidence`, catalog `file`) is
   **HTTPS** — plain HTTP is rejected at pack level even though `identity.canonical_url`
   tolerates it for legacy personal configs. (All 10 sources in the companion pack pass;
   colah's feed *content* links are http, but his `feed_url` is https, which is what the
   rule governs.)
4. No URL contains credentials, and no URL carries tracking parameters: if
   `identity.canonical_url(url) != url` after normalization, the pack is rejected with the
   offending parameter named. Curators ship clean URLs; users never inherit someone else's
   `utm_source`.
5. Every source `type` ∈ `KNOWN_TYPES`; every `channel` is a plausible channel id
   (`^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`, the loader's own rule).
6. `cadence.basis` present wherever `cadence` is claimed; `posts_per_month` ≥ 0.
7. An `enabled: true` rss source must have a `feed_url`; an enabled source of any type must
   have the locator its type requires (the loader's per-type rules, reused, not restated).

Liveness (network; results recorded, failure ≠ hard error):
8. For each enabled source with a `feed_url`: fetch exactly as
   `focu/source_collection.py` does (same UA, timeout, 2 MB cap) and parse with
   `parse_feed`. Outcomes: `live` (with item count and newest item date — which the
   installer compares against the pack's claimed `last_post_at`/cadence and reports drift),
   `dead` (HTTP error), `not_a_feed` (parse failure — the Jan Leike v0.1.0 case), or
   `unreachable` (timeout/DNS). Non-live → planned disabled (§4.2 step 4). Liveness is
   checked from the *installer's* environment, per the site AGENT_GUIDE ("a historical
   verification date is not a guarantee").
9. `homepage` liveness is checked with the same bounded fetch (any 2xx/3xx = live);
   failure downgrades to a warning for blog sources (the daily pipeline degrades
   gracefully on network failures by design) but is reported in the preview.

Warnings (install proceeds, preview shows them): missing `curator` (legacy packs),
missing `cadence`, `verified_at` older than 180 days, cadence drift vs. live feed,
pack `attention_estimate` mismatch vs. recomputed total.

## 7. Versioning and updates

- **Semver, with pack-specific meaning:** MAJOR = a source's locator changed or sources
  were removed (registry-affecting); MINOR = sources added or cadence/role metadata
  materially revised; PATCH = notes/typos. Curators state the bump in the catalog entry.
- **Pinning:** installs record the exact version + SHA-256 in the manifest (the reader side
  already pins by exact version in `ReaderStore.subscribe` — same contract, both
  registries). Nothing auto-updates. `focu pack list` shows "update available: 1.0.0 →
  1.1.0" as information only.
- **Update flow:** fetch the new version → validate → **source-level diff against the
  manifest snapshot**: added / removed / locator-changed / metadata-only. Preview shows the
  diff and the attention delta. On apply: added sources go through the normal install
  path (dedupe included); locator-changed sources are updated in place (identity changes —
  the preview must say so, because downstream dedupe keys on it); **removed sources are
  detached, not deleted** — they stay in `sources.yaml` as manual entries unless the user
  passes `--prune`, and `--prune` still respects the shared-source rule (§4.4). Rationale:
  a curator removing a source is a curation opinion; deleting a working subscription out
  from under the user is an attention decision the user didn't make.
- **Rollback of an update** = the same backup/restore machinery as install (§4.4); the
  manifest keeps one entry per (pack, version) install event, so history is auditable.
- **Catalog integrity:** the Exchange catalog (site `catalog.json` shape, extended) adds
  per-pack `version` and `sha256`. Install verifies the fetched pack against the catalog
  hash when a catalog was the source; direct file/URL installs print the hash for the
  record. The owner's site remains the first catalog; `focu pack catalog add` accepts any
  HTTPS catalog URL — curation is federated, trust is explicit (adding a catalog is itself
  a previewed action).

## 8. Module map — exactly what the implementation wave touches

| file | change |
|---|---|
| `focu/packs.py` | **NEW.** Schema validation, alias normalization, identity/dedupe planning, liveness (reusing `source_collection.parse_feed`), install/update/uninstall/restore, manifest I/O. Pure plan functions separated from file-writing, per the testability precedent in `focu/daily/`. |
| `schemas/source-pack.schema.json` | **NEW.** Normative JSON Schema for §3. |
| `focu/cli.py` | Add the `pack` subcommand group next to `reader` (line ~119) and `daily` (line ~121); thin argparse wrappers over `focu/packs.py`. |
| `focu/reader.py` | `packs()` gains validation + alias normalization via `focu.packs` (so the reader's Discover view and the CLI never disagree about what a pack *is*); `subscribe()`/`sources()` semantics unchanged. `canonical_url` divergence documented in §5 — unification is a follow-up, not this wave. |
| `focu/daily/config.py` | **No change.** `load_config()` is reused as the post-merge gate (§4.2 step 6). |
| `focu/daily/identity.py` | **No change.** `canonical_url` / `source_url` / `stable_id` are the dedupe substrate. |
| `focu/source_collection.py` | **No change.** `parse_feed` + fetch discipline reused by the liveness checker. |
| `focu/source_packs/anthropic-personal-blogs.json` | Later wave: replace with the v1.0.0 successor (companion deliverable this wave: `~/workspace/focu-dev/team/anthropic-people-pack.json`, same pack id). |
| `references/source-schema.md` | Add the pack→`sources.yaml` field mapping (§3.2) and a pointer to the pack schema. |
| `tests/test_packs.py` | **NEW.** Plan purity (dedupe vs. fixture registries), alias normalization, tracking-param rejection, manifest round-trip, uninstall shared-source preservation, update diff/prune semantics, post-merge `load_config` gate. |
| `tests/test_reader.py` | Existing contract tests (esp. `test_overlapping_packs_pin_membership_and_unsubscribe`) must pass unchanged — they pin the semantics §4.4 mirrors. |

Explicitly **not** touched: the daily pipeline's collection/selection code, the reader app
UI, and anything in production (`~/workspace/focu-live`, `~/focu-runtime`).

## 9. Worked example

`team/anthropic-people-pack.json` (companion deliverable) is schema v1 in practice:
10 verified sources (7 feed-enabled; 3 listed disabled because no usable feed exists —
Dario Amodei, Nicholas Carlini, Adam Jones), 9 unverified candidates with reasons, total
enabled attention estimate ≈ 5.5 posts/month dominated by one weekly newsletter. Against
Jerry's current production registry it dedupes to a no-op for Felix Rieseberg (already
subscribed) — the preview would show exactly that, which is the flow working as designed.

## 10. Open questions for PM / owner

1. **Name**: "Focu Exchange" is a working name (STATE.md) — owner to confirm or veto.
2. **Reader unification**: one registry or two? This design bridges reader subscriptions
   and `sources.yaml` via the manifest but does not merge them; a future wave could make
   `focu reader sources` export feed the same installer. Infra designer's call.
3. **Non-feed transports**: packs can list `youtube`/`x`/`linkedin` sources (the loader
   supports the types), but liveness/readiness semantics for session-based collectors are
   undefined here — deliberately deferred to the platform-collectors workstream; v1
   validation treats them as "listed, disabled unless the user already has the collector".
4. **Cadence freshness**: is a 180-day staleness warning the right threshold for
   people-packs, or should re-verification be part of `focu pack update` checks (cheap:
   one feed fetch per source)? Recommended: yes, fold re-verification into update previews.
