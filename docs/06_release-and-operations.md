# Release and operations

The application runs on a VPS behind Cloudflare Access. Actual access routes and configuration belong in the administrator-only `docs/07_private-operations.md`. Never let local and VPS workers control the same mailbox through separate databases. Do not use `make up` for production: that helper selects local mode.

## Release source and directories

The [release packager](../scripts/prepare-release.py), invoked by `make release`, owns clean-commit packaging, manifests, checksums, and exclusions. It prepares source for manual transfer; it does not replace the CI commit-fetch workflow. Archives exclude secrets, runtime data, and images; builds use lockfiles.

| VPS location | Ownership and purpose |
| --- | --- |
| `/opt/email-agentic/releases/<commit>` | Root-owned source, not writable by CI; retain the previous release for rollback. |
| `/opt/email-agentic/current` | Symlink to the active release. |
| `/etc/email-agentic` | Real configuration outside source archives; root-only, directories mode 700 and files mode 600. |
| `/var/backups/email-agentic` | Database dumps and private files, mode 700; encrypted upload to R2. |

Transfer manual archives over SSH with a pinned host key and verify SHA-256 before extraction. Transfer Google runtime tokens and actual Tunnel configuration separately; mount runtime tokens read-only through Compose secrets. Seed tokens, SSH keys, and Cloudflare API tokens must not enter containers. The `deploy` user has neither Docker access nor general sudo rights; CI uses only the restricted [deployment entry point](#deployment-permissions).

## Production configuration

Use the [production overlay](../infra/compose.production.yaml) with [base Compose](../infra/compose.yaml). The [deployment script](../scripts/deploy-production.sh) owns build, drain, backup, migration, cutover, and readiness ordering; do not maintain a separate command sequence that bypasses the reviewed script.

Load configuration through Compose's env-file mechanism. Do not `source` dotenv as shell code or print secrets through `docker compose config`; validate with `config --quiet`. Migrations must be explicit and preceded by a backup. Keep scheduling disabled during setup or data transfer until the database, token, and mailbox are confirmed.

Install Docker Engine/Compose from official sources for the host's Ubuntu release, checking version and CPU architecture before building. Install cloudflared on the host, validate ingress and Access JWT requirements, then follow the [Cloudflare service guide](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/as-a-service/linux/). Do not open additional firewall ports. See [Docker's production guidance](https://docs.docker.com/compose/how-tos/production/) for overlay conventions.

## Data transfer and rollout acceptance

Preserve research history, approvals, Gmail Draft IDs, and publication receipts when moving from local to VPS. Before the final dump, stop new work and the local worker, allow active sends to finish, and reconcile `running` or `unknown` actions separately. Back up both source and destination before restoring, including a baseline dump of a new destination. Never copy a live PostgreSQL data directory.

Use `pg_dump --format=custom --no-owner --no-acl`, inspect with `pg_restore --list`, and rehearse restoration into a separate database. Compare run/report/approval/action counts, sent/unknown states, checkpoints, and report content. Do not resume jobs or send email from the rehearsal database. Move to production only after those checks pass, with only the VPS worker active. Report export and attachment bytes travel with the PostgreSQL dump; include app-data in the snapshot as well.

Rollout acceptance requires readiness HTTP 200, API rejection without an Access JWT, hostname redirection to Access login, owner access to the web app/Grafana, and rejection of other accounts. Check existing email sources, reports, drafts, and send receipts. Do not send a test email; use only the next email explicitly approved by the user. Verify that container restarts retain data and do not duplicate sends. Build and configuration checks do not replace these live checks.

## Backup and rollback

The [backup script](../scripts/backup-production.sh), [service](../infra/systemd/email-agentic-backup.service), and [timer](../infra/systemd/email-agentic-backup.timer) own backup contents, scheduling, and retention. Backups must retain the release identity and a consistent database/app-data pair. Use encrypted restic storage on the prepared R2 destination; apply retention only after a successful upload. Do not configure age-based R2 lifecycle deletion for restic objects. See [restic backup guidance](https://restic.readthedocs.io/en/stable/040_backup.html).

The service reads `/etc/default/email-agentic-backup`; the separate restic password is at `/etc/email-agentic/restic-password`. Both are root-only. Inspect scheduling with `systemctl status email-agentic-backup.timer`, request an immediate backup with `systemctl start email-agentic-backup.service`, and read bounded results with `journalctl -u email-agentic-backup.service --since "1 hour ago" --no-pager`. Verify the restic snapshot and restore into a separate database/volume before enabling scheduling. A dump file alone does not prove recoverability. Retain a separate secure administrator copy of the restic password: losing it makes backups unrecoverable.

The [retention script](../scripts/retention-production.sh), [service](../infra/systemd/email-agentic-retention.service), and [timer](../infra/systemd/email-agentic-retention.timer) own cleanup after the daily backup schedule. Administrators install units in `/etc/systemd/system`, run `systemctl daemon-reload`, and enable `email-agentic-retention.timer` with `systemctl enable --now`. Inspect its status and bounded service journal. Backup failure must block cleanup; the script owns worker stop/restart and dump cleanup ordering. The CLI defaults to dry-run; consult `python -m email_agentic.platform.retention --help` inside the backend image. Cleaned payloads can remain in backups until backup retention expires. Cleanup does not delete Google email or calendar data.

For code rollback, disable retention if the target release does not support cleanup, stop the worker, repoint `current`, and use images with the previous release ID via `--no-build`. Do not delete volumes or prune images before stability is confirmed. This route requires schema compatibility. Otherwise, back up the current state, restore a tested matching database/app-data pair, and reconcile email sent after the backup before restarting the worker. Never replay publications that already occurred. An initial deployment has no previous release: stop the application/connector and preserve volumes and backups for repair.

Automated deployment logs are root-only at `/var/log/email-agentic-deploy/<commit>.log`. For application logs, select the production Compose files and use `logs --since 30m --tail 100 <service>`; for the connector, use a bounded `journalctl -u cloudflared` query. Select the intended service/run and time zone, minimize output, and never publish raw email, prompts, or tokens. Actual host, account, and credential routes remain in the private guide.

## CI/CD and deployment boundaries

The [CI/CD workflow](../.github/workflows/ci-cd.yml) owns triggers, verification commands, and deployment eligibility. Tests use a separate database without production Google credentials, golden answers, or production data. CI success does not establish integrated rollout or PRD acceptance.

Changes go through a work branch, pull request, successful `verify` check, and squash merge to `main`; see [contributing and quality](08_contributing-and-quality.md). Required database-backed layers must fail when their database is unavailable. Browser E2E uses the real test API and PostgreSQL; pull requests must not receive production secrets.

Deploy only after verification on the branch and environment permitted by the workflow. Do not cancel an active deployment. VPS locking and the main-HEAD check prevent an older run from overwriting a newer cutover; their executable owner is the deployment script.

Deployment and retention share `/run/lock/email-agentic-deploy.lock` before choosing a release or stopping the worker. When upgrading a host that used separate locks, an administrator must stop retention scheduling, wait for active work to finish, reinstall the reviewed root-owned deployment entry point, and update the reviewed retention script before enabling scheduling again. Editing repository source alone does not update the installed entry point.

## Deployment permissions

Environment secrets are `VPS_HOST`, `VPS_PORT`, `VPS_DEPLOY_SSH_KEY`, and `VPS_KNOWN_HOSTS`. Pin the host key from a verified administrator connection; CI must not trust a fresh `ssh-keyscan` result. An administrator must confirm a changed host/key fingerprint through the provider console before updating the secret.

The `deploy` user must not join Docker or general sudo groups. [Restricted sudoers](../infra/sudoers/email-agentic-deploy) permits only `/usr/local/sbin/email-agentic-deploy`, the root-owned installation of the [deployment script](../scripts/deploy-production.sh). That entry point accepts a full commit ID or `--check` and verifies the fixed repository's `main` HEAD. CI must not upload scripts, archives, or configuration for root to execute. An administrator installs changes to the entry point from reviewed source; CI cannot change its own privileges.

Install the script with `install -o root -g root -m 755 scripts/deploy-production.sh /usr/local/sbin/email-agentic-deploy`. Validate sudoers using `visudo -cf infra/sudoers/email-agentic-deploy`, then install it at `/etc/sudoers.d/email-agentic-deploy` with mode 440. As `deploy`, run `sudo -n /usr/local/sbin/email-agentic-deploy --check`. The [VPS connectivity workflow](../.github/workflows/vps-connectivity.yml) checks connection and permission boundaries without deploying.

## Deployment failures

The deployment script owns automatic recovery. It must not automatically restore a database after schema changes because doing so can lose send receipts. An administrator follows the backup/rollback route and reconciles data before enabling the worker.

Manage CI secrets in repository Settings → Environments → vps. Actual account/host configuration and access permissions belong in the private guide. Inspect the commit-specific deployment log above; do not publish private logs in issues or pull requests.
