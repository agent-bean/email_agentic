#!/usr/bin/env bash
# Production retention runs only after an encrypted backup succeeds.
set -euo pipefail
umask 077
test "$(id -u)" = 0
exec 9>/run/lock/email-agentic-retention.lock
flock -n 9 || { echo 'Retention is already running'; exit 1; }
cd /opt/email-agentic/current
export RELEASE_ID COMPOSE_ENV_FILES=/etc/email-agentic/runtime.conf
RELEASE_ID=$(cat .release-id)
[[ "$RELEASE_ID" =~ ^[a-f0-9]{40}$ ]]
compose=(docker compose -f infra/compose.yaml -f infra/compose.production.yaml)
systemctl start email-agentic-backup.service
# Stop new claims; active jobs are protected by the service as well.
"${compose[@]}" stop worker >/dev/null
trap '"${compose[@]}" up -d --no-build worker >/dev/null' EXIT
"${compose[@]}" run --rm --no-deps -T --entrypoint python migrate \
    -m email_agentic.platform.retention --apply --backup-dir /data/backups
