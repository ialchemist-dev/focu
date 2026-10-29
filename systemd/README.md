# Runtime unit generation

Use `focu host doctor` on the target host. `focu host configure` generates reader and sync units with real absolute paths and an exact HTTPS origin. It does not install services, start Tailscale, authorize accounts or change tailnet permissions.

Create a private environment file (mode 600) containing `FOCU_GITHUB_TOKEN=...` (or `GH_TOKEN`) for a fine-grained token limited to the private metadata repository; Git also needs push access, such as a repository-scoped SSH key. Drive credentials are in a separate owner-only JSON file. Do not put either file in this directory or commit credentials.

After local testing, copy generated units to `/etc/systemd/system/`, run `systemctl daemon-reload`, restart `focu-reader` and enable/start `focu-sync`. Provision the Tailscale node and use **Serve**, not Funnel. All services must run as the owning user, or an explicitly configured service user with access to only the required files. The generator omits `User=` so the installer must use a user service or add `User=` before system-wide installation; do not silently broaden privileges.

Save the non-secret generated units under the existing workspace service backup directory, because a Muse VM replacement may lose `/etc`. Node identity, credentials, hostname stability and platform-persistent paths need host verification. A generated unit is not proof of phone connectivity.
