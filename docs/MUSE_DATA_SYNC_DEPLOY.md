# Muse deployment handoff: durable data sync

This is deployment/acceptance of implemented Focu 0.4.0 code, not a request to develop missing adapters. Read DATA_FLOW.md first.

## Preserve the current installation

Keep the current acceptance database, published cards/media, production DB and old daily cron. Make a consistent backup before the additive database migration. Use a clean checkout of the approved release/PR commit and a checkout-local venv; run bootstrap and install `.[daily]`. Confirm version and module location. If working in an existing dirty checkout, preserve it and use a separate clone.

## Collect only missing host/account inputs

1. Authorized private Google Drive folder + owner-only OAuth JSON matching `examples/drive-private.example.json`. Reuse an existing suitable host authorization; never extract connector tokens. If no suitable authorization exists, guide the user through their Google OAuth app consent. Do not request secrets in chat. Folder must be created/selected within that app's scopes and remain private.
2. Dedicated private GitHub metadata repo (for example `focu-data`) with initial commit and named branch, clean local clone, push access, and a repository-scoped `FOCU_GITHUB_TOKEN`/`GH_TOKEN` for privacy verification. Never store this data in public `ialchemist-dev/focu`.
3. Existing tailnet account/device authorization and the real HTTPS Serve hostname. Run `focu host doctor`; verify target VM permissions, userspace/TUN options, reboot behavior and persistence. Do not enable Funnel or weaken network isolation. Missing platform permission must be reported rather than bypassed.

Use absolute paths throughout. Store the Git token in a mode-600 private environment file and the Drive OAuth JSON in a mode-600 file. Tailscale state and resumable session files need protected persistent storage. No account authorization or credentials have been provisioned by the code change itself.

## Run the delivered implementation

Load the private runtime environment without printing it. Run:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest discover -s tests/unit -v
.venv/bin/focu --version
.venv/bin/focu host doctor
.venv/bin/focu --db ABS_DB sync run --repo ABS_PRIVATE_REPO --media-root ABS_MEDIA_ROOT --drive-config ABS_PRIVATE_JSON
.venv/bin/focu --db ABS_DB sync status
```

Check a successful remote checkpoint before deleting any cache in an isolated test. Do not delete original acceptance media merely to test recovery. Original cover fetch failures are reported as optional warnings; do not replace them with unrelated images.

Use the existing Tailscale installation or provision the official client with the user's account authorization. Verify the current client help and use Serve privately, typically:

```bash
tailscale serve --bg http://127.0.0.1:8765
```

The exact HTTPS URL returned by Serve is PUBLIC_ORIGIN below; never guess it. Then generate units:

```bash
.venv/bin/focu host configure --checkout ABS_CHECKOUT --db ABS_DB \
  --media-root ABS_MEDIA_ROOT --repo ABS_PRIVATE_REPO \
  --drive-config ABS_PRIVATE_JSON --environment-file ABS_PRIVATE_ENV \
  --public-origin PUBLIC_ORIGIN --output-dir ABS_CHECKOUT/systemd/generated
```

Inspect the generated units and run them with the existing owning service account. For system units, explicitly set `User=` appropriately; for a user service adjust target/install placement. Preserve the old reader unit for rollback. Install/reload/restart the reader and start the sync worker through the existing process manager. Do not run a second sync writer. Back up non-secret service definitions in the persistent workspace, not only /etc. Verify the generated command works before enabling restart/autostart.

## Live acceptance

- Keep the five existing acceptance cards; inspect original covers and language defaults.
- From an authorized second device, open the private HTTPS URL. Verify GET **and POST**, save/read/undo/archive, playback resume and 206 seeking. Unapproved Origin/Host must still fail.
- Verify the UI goes from Sync pending to Backed up after a successful push; inspect latest remote checkpoint/time. Pending changes on a disappearing VM are not durable.
- Check the private repo contains catalog/state/event JSON, not binaries or secrets. Check Drive artifacts' hashes and repeated sync does not duplicate completed files.
- In a separate empty recovery directory, run `focu --db NEW_DB sync restore --repo ABS_PRIVATE_REPO --media-root NEW_MEDIA --drive-config ABS_PRIVATE_JSON`, first without eager media downloads. Start a temporary loopback reader using NEW_DB and NEW_MEDIA, verify audio can refill its empty cache and play/seek. The production and acceptance originals must remain untouched.
- Verify Google authorization/token expiry, network interruption and Git push error behavior without posting credentials or intentionally damaging the real repo. The offline tests already cover injected failures.

Deliver the real access URL, required iPhone tailnet step, running version/commit, private Drive folder and metadata repository links, last checkpoint, verification results and stop/restart/rollback commands. If account authorization or the target platform prevents live completion, report the precise missing input; do not rewrite the finished storage/sync system or claim mock tests were live cloud acceptance.
