# Durable data flow (0.4.0)

Implemented modules: `drive_storage`, `git_journal`, `sync_events`, `data_sync`, `cover_archive`, `hosting`. This is a single-owner, single active sync-writer system. A second reading client talks to the same API; it does not write Git. Running two sync hosts concurrently is not supported.

## Ownership and durable storage

| Data | Live location | Durable location |
| --- | --- | --- |
| Research reports, transcripts, evidence, published audio/video | SQLite + configured media root | Private Drive artifacts, verified by size and checksum |
| Original cover bytes | Media cache | Private Drive when source image is accessible |
| Content directory and artifact IDs/hashes | SQLite | Private Git `focu/catalog.json` |
| Read/save/archive/progress state | SQLite | Git state checkpoint + immutable event files |
| Full research database baseline (including intents/evidence/raw queue) | SQLite consistent backup | Compressed private Drive snapshot |
| OAuth tokens, Git token, upload session URIs, Tailscale identity | Private persistent host files | Host secret storage; never Git/catalog/UI |

The state API writes changes and an outbox event in one SQLite transaction. Each event has a unique ID and server sequence. Clients supply an expected item revision; stale clients get HTTP 409 rather than overwriting another device. Duplicate event retries return the existing outcome without replaying changes. Completed/read_at, saved/saved_at, archived/archived_at and position_seconds are separate fields. User archiving is not an upload-success flag.

`focu sync run` takes a kernel writer lock and captures a consistent SQLite snapshot. It uploads registered reports, evidence, podcast derivative text, audio/video and available covers, verifies remote byte size and SHA-256 or MD5, then publishes the catalog and captured event prefix to private Git. Only a successful Git push acknowledges that prefix. New events arriving during upload/push remain pending. Failures retain events and report a visible sync error. A worker batches changes every 60 seconds by default. Phone playback writes position about every 15 seconds and on pause/end; it does not create one Git commit per second.

Binary artifacts never enter Git. Large captured source text is stripped from the Git catalog and remains in Drive's database baseline. A baseline is uploaded when content/research changes; reading-only updates reuse the baseline and update Git state metadata. Restore overlays Git's latest states/covers/subscriptions/events onto that baseline. WAL databases are copied through SQLite backup before compression, not copied as live files.

Drive uploads use resumable 8 MiB chunks, stable artifact/content keys, completed-object lookup and private local session checkpoints. Retry queries the server-confirmed offset. Session URLs must persist on the host and are treated as secrets. If the host loses an unfinished upload session, it can restart that upload; orphaned incomplete sessions are not a committed checkpoint. Folder privacy and writable capability are checked; public/domain or unapproved shared permissions fail closed.

Git sync checks that the GitHub origin is private, checks for a clean checkout and refuses upstream divergence. It uses ordinary fast-forward push, never force push. A committed-but-not-pushed local checkpoint can be retried. Unexpected edits or another writer require operator reconciliation; they are not automatically discarded/rebased.

## Access and media cache

Reader remains bound to 127.0.0.1. `reader serve --public-origin https://ACTUAL-NODE.ts.net --drive-config PRIVATE_JSON` accepts that exact HTTPS origin and Host, plus local development access. It does not trust arbitrary forwarded identity headers or change tailnet policies. Use Tailscale **Serve**, not Funnel. Tailnet authorization and persistent node setup are deployment tasks, not capabilities claimed by the Python package.

When an audio/video file is missing, the server looks up its verified Drive record, downloads into an atomic local cache, verifies size/hash and serves the existing same-origin `/media` endpoint with byte ranges. The browser never receives OAuth or Git credentials. First playback after a cache miss waits for the full artifact to download; this implementation is not an upstream chunk-by-chunk streaming proxy. `/cover` similarly serves mirrored original images. Unavailable original covers remain explicit catalog warnings and retain text-cover fallback. Cover mirroring rejects private-network DNS results and redirects, accepts HTTPS raster images only and caps responses at 10 MiB; deployment egress restrictions should also block private networks because DNS prevalidation alone is not a complete defense against DNS rebinding.

UI indicates Local only, Sync pending, Sync needs attention, Backed up or Offline, with last confirmed remote checkpoint time. It polls for other-client changes every 15 seconds while visible. Offline edits are not accepted/queued in the browser; an unavailable API is reported honestly. Reading-state operations require the server. Data not yet pushed off the VM can be lost if that VM disappears; pending is not a backup guarantee. Drive/Git preserve recovery data but do not keep the UI online if its host is off.

## Credentials and setup

Create a private Drive folder using the same authorized Google OAuth app (prefer `drive.file` for app-created/explicitly selected files). Do not extract credentials from a ChatGPT connector. The adapter needs a refreshable OAuth configuration; see `examples/drive-private.example.json`. Store the actual file outside Git with mode 600. If the folder deliberately has additional trusted collaborators, explicitly list only their permission IDs under `allowed_permission_ids`; anyone/domain sharing is never accepted.

Use a separate private GitHub data repository, with an initial commit and a named branch. Clone it into a dedicated clean directory. Runtime Git requires push credentials (for example a repo-scoped SSH key) and `FOCU_GITHUB_TOKEN` or `GH_TOKEN` to verify repository privacy through the GitHub API. Limit credentials to this data repository. Do not reuse the public Focu code repo for personal metadata.

```bash
.venv/bin/focu --db ABS_DB sync run --repo ABS_PRIVATE_REPO --media-root ABS_MEDIA_ROOT --drive-config ABS_PRIVATE_JSON
.venv/bin/focu --db ABS_DB sync status
.venv/bin/focu --db ABS_DB sync watch --repo ABS_PRIVATE_REPO --media-root ABS_MEDIA_ROOT --drive-config ABS_PRIVATE_JSON --interval 60
```

Artifacts are currently registered through published reader items and their linked delivery/evidence records. Publish a batch after generation to register its audio/video. The database baseline preserves other research records, but arbitrary unregistered files elsewhere on disk are not silently uploaded. Existing source material, secrets and unrelated files are not swept into a generic recursive sync.

## Recovery

Stop the old sync writer before moving ownership to another host. Clone the latest private metadata repository; provision the same scoped credentials and Drive access. Restore only to a fresh database path:

```bash
.venv/bin/focu --db /absolute/NEW/state.sqlite3 sync restore \
  --repo ABS_PRIVATE_REPO --media-root /absolute/NEW/media \
  --drive-config ABS_PRIVATE_JSON --download-media
```

Omit `--download-media` for lazy cache recovery. Existing destination databases are refused. SQL identifiers used for metadata restore are allowlisted. The downloaded baseline must match Git's recorded size/hash and pass SQLite integrity checking. Latest saved/read/archive/progress states are restored from Git, not stale baseline state. Upload checkpoint state and remote highwater are restored; already synced events do not reappear as pending. Keep the prior host/database until live acceptance passes.

## Deployment

`focu host doctor` reports installed Tailscale/backend status, TUN visibility and basic host tools; it does not claim peer connectivity or persistent VM storage. Missing TUN does not prove userspace Serve works or fails. `focu host configure` creates concrete systemd units; it neither installs them nor authorizes accounts. See `MUSE_DATA_SYNC_DEPLOY.md` for the install-only handoff.

## Verification boundary

Tests run real local Git push/fetch against a bare repository plus deterministic Drive transport/storage fixtures. They cover state atomicity/revisions/idempotence, network/push failure, concurrent new events, cache removal/byte ranges, private-target rejection, WAL baseline recovery, new-content checkpoints, cover recovery, checksum failure and resumable upload continuation. They do not claim live Google OAuth, the user's folder/repo, physical iPhone use or Muse Tailscale support were verified in this environment.

Official protocol references: [Drive uploads](https://developers.google.com/workspace/drive/api/guides/manage-uploads), [Drive files/checksums](https://developers.google.com/workspace/drive/api/reference/rest/v3/files), [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve).
