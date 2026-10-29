#!/usr/bin/env bash
# Install root-owned; CI may invoke this entry point, never a general shell.
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
umask 077
test "$(id -u)" = 0 || { echo 'Root-owned deploy entry point required'; exit 1; }
[[ $# = 1 ]] || { echo 'Expected one tested main commit'; exit 1; }
base=/opt/email-agentic
repository=https://github.com/agent-bean/email_agentic.git
export COMPOSE_ENV_FILES=/etc/email-agentic/runtime.conf
if [[ "$1" = --check ]]; then
  test -r "$COMPOSE_ENV_FILES"
  test -L "$base/current"
  systemctl is-enabled --quiet email-agentic-backup.timer
  docker info >/dev/null 2>&1
  printf 'Deploy entry point ready; current release: %s\n' "$(cat "$base/current/.release-id")"
  exit 0
fi
revision=$1
[[ "$revision" =~ ^[a-f0-9]{40}$ ]] || { echo 'Invalid commit ID'; exit 1; }
exec 9>/run/lock/email-agentic-deploy.lock
flock -n 9 || { echo 'Another deployment is running'; exit 1; }
previous=$(readlink -f "$base/current")
[[ "$previous" = "$base/releases/"* ]] && test -f "$previous/.release-id"
install -d -m 700 "$base/source.git" /var/log/email-agentic-deploy
log=/var/log/email-agentic-deploy/$revision.log
exec 3>&1
exec >"$log" 2>&1
stage() { printf '%s\n' "$1" >&3; }
stopped=false
schema_changed=false
recover() {
  result=$?
  trap - EXIT
  if (( result != 0 )); then
    if [[ "$stopped" = true && "$schema_changed" = false ]]; then
      ln -sfn "$previous" "$base/current"
      cd "$previous"
      export RELEASE_ID
      RELEASE_ID=$(cat .release-id)
      docker compose -f infra/compose.yaml -f infra/compose.production.yaml up -d --no-build --wait web api worker &&
        stage 'Previous code restored; deployment failed.'
    elif [[ "$stopped" = true ]]; then
      "${compose[@]}" stop worker api || true
      stage 'Deployment failed after a schema change; admin must inspect backup before restoring.'
    fi
    stage "Deployment failed; administrator log: $log"
  fi
  exit "$result"
}
trap recover EXIT
if [[ ! -f "$base/source.git/HEAD" ]]; then
  git init --bare "$base/source.git"
fi
git -C "$base/source.git" fetch --no-tags --depth=1 "$repository" refs/heads/main
head=$(git -C "$base/source.git" rev-parse FETCH_HEAD)
[[ "$head" = "$revision" ]] || { stage 'Refusing a commit that is no longer main HEAD'; exit 1; }
release=$base/releases/$revision
if [[ "$(cat "$previous/.release-id")" = "$revision" ]]; then
  curl --fail --silent --show-error http://127.0.0.1:8000/health/ready >/dev/null
  stage "Already healthy on $revision"
  exit 0
fi
# Each failed attempt gets a fresh directory, preserving its diagnostic source.
if [[ -e "$release" ]]; then
  mv "$release" "$release.failed-$(date -u +%Y%m%dT%H%M%S%N)"
fi
mkdir -m 700 "$release"
git -C "$base/source.git" archive "$revision" -- apps/backend apps/web infra \
  scripts/backup-production.sh scripts/retention-production.sh .dockerignore |
  python3 -c 'import sys,tarfile; tarfile.open(fileobj=sys.stdin.buffer,mode="r|").extractall(sys.argv[1],filter="data")' "$release"
printf '%s\n' "$revision" > "$release/.release-id"
ln -s /etc/email-agentic/secrets "$release/.secrets"
cd "$release"
export RELEASE_ID=$revision
compose=(docker compose -f infra/compose.yaml -f infra/compose.production.yaml)
"${compose[@]}" config --quiet
"${compose[@]}" build api web
stage 'Exact main source fetched; backend and web images built.'
# Refuse a busy cutover. A new request remains persisted for the next worker.
for attempt in $(seq 1 60); do
  active=$(docker exec email-agentic-vps-postgres-1 psql -U email_agentic -d email_agentic -At -c "SELECT count(*) FROM jobs WHERE status='running'")
  [[ "$active" = 0 ]] && break
  sleep 3
done
[[ "$active" = 0 ]] || { stage 'Active jobs did not drain; current release kept running'; exit 1; }
stopped=true
"${compose[@]}" stop --timeout 900 worker
# Backup is taken with the worker stopped, before any migration writes.
systemctl start email-agentic-backup.service
stage 'Encrypted backup completed before migration.'
"${compose[@]}" stop api
if ! diff -qr "$previous/apps/backend/migrations" "$release/apps/backend/migrations"; then
  schema_changed=true
fi
"${compose[@]}" run --rm migrate
ln -sfn "$release" "$base/current"
"${compose[@]}" up -d --no-build --wait web api worker
curl --retry 10 --retry-all-errors --retry-delay 2 --fail --silent --show-error http://127.0.0.1:8000/health/ready >/dev/null
stopped=false
stage "Deployed and healthy: $revision"
