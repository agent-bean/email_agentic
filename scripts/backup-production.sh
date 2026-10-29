#!/usr/bin/env bash
# Credentials are inherited from the root-owned service environment.
set -euo pipefail
umask 077
: "${RESTIC_REPOSITORY:?Missing backup repository}" "${RESTIC_PASSWORD_FILE:?Missing backup password file}"
: "${AWS_ACCESS_KEY_ID:?Missing R2 access key}" "${AWS_SECRET_ACCESS_KEY:?Missing R2 secret key}"
: "${COMPOSE_ENV_FILES:?Missing production configuration path}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-auto}"
test "$(id -u)" = 0
exec 9>/run/lock/email-agentic-backup.lock
flock -n 9 || { echo 'Another backup is running'; exit 1; }
cd /opt/email-agentic/current
export RELEASE_ID
RELEASE_ID=$(cat .release-id)
[[ "$RELEASE_ID" =~ ^[a-f0-9]{40}$ ]]
compose=(docker compose -f infra/compose.yaml -f infra/compose.production.yaml)
command -v restic >/dev/null
restic cat config >/dev/null
snapshot="/var/backups/email-agentic/$(date -u +%Y%m%dT%H%M%S%N)"
install -d -m 700 "$snapshot"
"${compose[@]}" exec -T postgres pg_dump -U email_agentic -d email_agentic --format=custom --no-owner --no-acl > "$snapshot/database.dump"
test -s "$snapshot/database.dump"
"${compose[@]}" exec -T postgres pg_restore --list < "$snapshot/database.dump" >/dev/null
"${compose[@]}" run --rm --no-deps -T --entrypoint tar migrate -C /data --exclude=./backups -cf - . > "$snapshot/app-data.tar"
tar -tf "$snapshot/app-data.tar" >/dev/null
printf '%s\n' "$RELEASE_ID" > "$snapshot/release-id"
restic backup --tag email-agentic-production --group-by host,tags "$snapshot"
restic forget --tag email-agentic-production --group-by host,tags --keep-daily 7 --prune
find /var/backups/email-agentic -mindepth 1 -maxdepth 1 -type d -mtime +7 -exec rm -rf -- {} +
echo 'Backup uploaded. Restore validation is a separate operation.'
